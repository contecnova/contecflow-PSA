/**
 * Configuración → Finanzas → Clientes internos (22-11-2026, capacidad `interno.cargos`).
 *
 * Servicios compartidos (`/internal-clients/shared-costs`): importe mensual y
 * criterio de reparto entre unidades (usuarios, tickets, licencias, software o
 * porcentajes fijos), con vista previa del reparto de un mes. Es ajuste, no
 * operación: por eso vive aquí y no en `/internal-clients` (configuración única).
 * También la cuenta de TI del asiento de los cargos (`INTERNAL_IT_ERP_ACCOUNT`,
 * ajuste por empresa del grupo `presupuestos`; el servidor la valida).
 * Ver docs/CLIENTES_INTERNOS.md §4 y §11.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, Eye, Pencil, Plus, Share2, Trash2 } from 'lucide-react'
import { Button, Card, Checkbox, IconButton, Input, Modal, Select, Spinner, TablaSimple, Textarea } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import SeccionDeAjustes from '../settings-sections/SeccionDeAjustes'
import { confirmar } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { clientsApi, unwrapList } from '../../services/api'
import { settingsApi } from '../../services/api/settings'
import { clientesInternosApi } from '../../services/api/clientesInternos'
import type { CriterioDeReparto, ServicioCompartido, ServicioCompartidoIn } from '../../services/api/clientesInternos'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { STALE_REFERENCE_DATA_MS } from '../../constants/timings'
import { extractErr, fmtNumber } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useT } from './comunes'
import { CRITERIOS_DE_REPARTO, etiquetaInterna, mesActual, numeroONull, textoONull } from './logica'

const CLAVE = ['internal-clients', 'shared-costs']

/** Unidades internas (clientes con `kind=interno`) para los porcentajes fijos. */
function useUnidadesInternas() {
  const { data = [] } = useQuery({
    queryKey: ['clients', { kind: 'interno', todas: true }],
    queryFn: () => clientsApi.list({ kind: 'interno', page_size: 500 }).then(r => unwrapList(r) as { id: string; name: string }[]),
    staleTime: STALE_REFERENCE_DATA_MS,
  })
  return data
}

function FormularioDeServicio({ item, onClose }: { item: ServicioCompartido | null; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const unidades = useUnidadesInternas()
  // 23-11-2026: la moneda por defecto es la de la empresa (antes 'EUR' fijo).
  const monedaEmpresa = useFormatoMoneda().moneda
  const [f, setF] = useState({
    name: item?.name || '', description: item?.description || '', monthly_amount: item ? String(item.monthly_amount) : '',
    currency: item?.currency || monedaEmpresa, criterion: (item?.criterion || 'usuarios') as CriterioDeReparto, is_active: item?.is_active ?? true,
  })
  const [cuotas, setCuotas] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(item?.fixed_shares || {}).map(([k, v]) => [k, String(v)])),
  )
  const suma = Object.values(cuotas).reduce((s, v) => s + (numeroONull(v) ?? 0), 0)
  const set = (k: 'name' | 'description' | 'monthly_amount' | 'currency') => (e: { target: { value: string } }) => setF(x => ({ ...x, [k]: e.target.value }))
  const guardar = useMutation({
    mutationFn: () => {
      const fijas = Object.fromEntries(Object.entries(cuotas).map(([k, v]) => [k, numeroONull(v)]).filter(([, v]) => v != null && (v as number) > 0)) as Record<string, number>
      const d: ServicioCompartidoIn = {
        name: f.name.trim(), description: textoONull(f.description), monthly_amount: numeroONull(f.monthly_amount) ?? 0,
        currency: f.currency.trim().toUpperCase() || monedaEmpresa, criterion: f.criterion, fixed_shares: f.criterion === 'fijo' ? fijas : null, is_active: f.is_active,
      }
      return item ? clientesInternosApi.editarServicioCompartido(item.id, d) : clientesInternosApi.crearServicioCompartido(d)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: CLAVE }); toast.success(t('internos.guardado')); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const sumaMal = f.criterion === 'fijo' && Math.abs(suma - 100) > 0.01
  return (
    <Modal open onClose={onClose} width={620} title={item ? t('internos.editar_servicio') : t('internos.nuevo_servicio')}>
      <div className="u-stack-8">
        <Input label={t('internos.nombre')} required value={f.name} onChange={set('name')} />
        <Textarea label={t('internos.descripcion')} value={f.description} onChange={set('description')} rows={2} />
        <div className="int-rejilla">
          <Input label={t('internos.importe_mensual')} type="number" min={0} step="any" required value={f.monthly_amount} onChange={set('monthly_amount')} />
          <Input label={t('internos.moneda')} value={f.currency} maxLength={3} onChange={set('currency')} />
          <Select label={t('internos.criterio')} value={f.criterion} placeholder={false} onChange={e => setF(x => ({ ...x, criterion: e.target.value as CriterioDeReparto }))}
            options={CRITERIOS_DE_REPARTO.map(c => ({ value: c, label: etiquetaInterna(t, 'criterio_', c) }))} />
        </div>
        <p className="int-nota">{t(`internos.criterio_${f.criterion}_d`)}</p>
        {f.criterion === 'fijo' && (
          <Card className="int-bloque">
            <div className="int-bloque__titulo">{t('internos.cuotas_fijas')}</div>
            {!unidades.length ? <p className="u-text2-sm">{t('internos.sin_unidades')}</p> : (
              <div className="int-rejilla">
                {unidades.map(u => (
                  <Input key={u.id} label={u.name} type="number" min={0} max={100} step="any" value={cuotas[u.id] ?? ''}
                    onChange={e => setCuotas(c => ({ ...c, [u.id]: e.target.value }))} />
                ))}
              </div>
            )}
            <div className="int-total">
              <span>{t('internos.suma')}</span>
              <StatusBadge kind={sumaMal ? 'danger' : 'success'} caps={false}>{`${fmtNumber(suma, 2)}%`}</StatusBadge>
            </div>
          </Card>
        )}
        <Checkbox checked={f.is_active} onChange={v => setF(x => ({ ...x, is_active: v }))} label={t('internos.activo')} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending}
            disabled={!f.name.trim() || numeroONull(f.monthly_amount) == null || sumaMal || guardar.isPending}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function VistaPrevia({ item, onClose }: { item: ServicioCompartido; onClose: () => void }) {
  const t = useT()
  const fmtMoneda = useFormatoMoneda()
  const [periodo, setPeriodo] = useState(mesActual())
  const { data, isLoading, error } = useQuery({
    queryKey: [...CLAVE, 'allocation', item.id, periodo],
    queryFn: () => clientesInternosApi.reparto(item.id, periodo),
    enabled: !!periodo,
    retry: false,
  })
  return (
    <Modal open onClose={onClose} width={620} title={t('internos.vista_previa_de', { nombre: item.name })}>
      <div className="u-stack-8">
        <div className="int-barra__filtros">
          <Input label={t('internos.periodo')} type="month" value={periodo} onChange={e => setPeriodo(e.target.value)} />
        </div>
        {isLoading ? <Spinner /> : error ? <p className="u-field-error">{extractErr(error, GENERIC_ERROR_FALLBACK)}</p> : data && (
          !data.shares.length ? <p className="u-text2-sm">{t('internos.reparto_vacio')}</p> : (
            <>
              <div className="u-scroll-x">
                <TablaSimple claseTabla="u-table" etiqueta={t('internos.reparto')}>
                  <thead><tr>{[t('internos.col_unidad'), t('internos.col_driver'), t('internos.col_pct'), t('internos.col_importe')].map(h => <th key={h} scope="col" className="int-th">{h}</th>)}</tr></thead>
                  <tbody>
                    {data.shares.map(s => (
                      <tr key={s.client_id}>
                        <td className="int-td">{s.client_name}</td>
                        <td className="int-td int-td--num">{s.driver != null ? fmtNumber(s.driver, 2) : '—'}</td>
                        <td className="int-td int-td--num">{`${fmtNumber(s.pct, 2)}%`}</td>
                        <td className="int-td int-td--num">{fmtMoneda(s.amount, { moneda: data.currency })}</td>
                      </tr>
                    ))}
                  </tbody>
                </TablaSimple>
              </div>
              <div className="int-total"><span>{t('internos.total')}</span><span>{fmtMoneda(data.total, { moneda: data.currency })}</span></div>
            </>
          )
        )}
      </div>
    </Modal>
  )
}

const GRUPO_CUENTA = 'presupuestos'
const CLAVE_CUENTA = 'INTERNAL_IT_ERP_ACCOUNT'

/** Cuenta contable o centro de TI que recibe el haber de los asientos de cargos internos. */
function CuentaDeTi() {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data, isError } = useQuery({
    queryKey: ['runtime-flags', GRUPO_CUENTA],
    queryFn: () => settingsApi.runtimeGroup(GRUPO_CUENTA).then(r => r.data),
    retry: false,
  })
  const actual = data?.items?.find(i => i.key === CLAVE_CUENTA)
  const [valor, setValor] = useState('')
  useEffect(() => { setValor(actual?.value == null ? '' : String(actual.value)) }, [actual?.value])
  const guardar = useMutation({
    mutationFn: () => settingsApi.setRuntime(GRUPO_CUENTA, CLAVE_CUENTA, valor.trim()),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['runtime-flags', GRUPO_CUENTA] }); toast.success(t('internos.guardado')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const sucio = String(actual?.value ?? '') !== valor
  return (
    <SeccionDeAjustes icon={<BookOpen size={18} />} title={t('internos.cuenta_ti')} description={t('internos.cuenta_ti_d')}>
      {isError ? <p className="u-field-error">{t('internos.cuenta_ti_error')}</p> : (
        <div className="int-barra">
          <Input className="u-flex1" label={t(`ajuste_clave.${CLAVE_CUENTA}`)} value={valor} maxLength={40}
            placeholder={t('internos.cuenta_ti_ejemplo')} onChange={e => setValor(e.target.value)} />
          <Button size="sm" variant={sucio ? 'primary' : 'secondary'} disabled={!sucio || guardar.isPending}
            loading={guardar.isPending} onClick={() => guardar.mutate()}>{t('common.save')}</Button>
        </div>
      )}
      {!isError && !String(actual?.value ?? '').trim() && <p className="int-nota">{t('internos.cuenta_ti_vacia')}</p>}
    </SeccionDeAjustes>
  )
}

export default function ConfigClientesInternos() {
  return (
    <>
      <CuentaDeTi />
      <ServiciosCompartidos />
    </>
  )
}

function ServiciosCompartidos() {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const fmtMoneda = useFormatoMoneda()
  const [editando, setEditando] = useState<ServicioCompartido | null | 'nuevo'>(null)
  const [viendo, setViendo] = useState<ServicioCompartido | null>(null)
  const { data: servicios = [], isLoading } = useQuery({ queryKey: CLAVE, queryFn: () => clientesInternosApi.serviciosCompartidos() })
  const borrar = useMutation({
    mutationFn: (id: string) => clientesInternosApi.borrarServicioCompartido(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: CLAVE }); toast.success(t('internos.borrado')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <SeccionDeAjustes icon={<Share2 size={18} />} title={t('internos.servicios_compartidos')} description={t('internos.servicios_compartidos_d')}>
      <div className="int-barra">
        <span />
        <Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando('nuevo')}>{t('internos.nuevo_servicio')}</Button>
      </div>
      {isLoading ? <Spinner /> : !servicios.length ? <p className="u-text2-sm int-mt">{t('internos.sin_servicios')}</p> : (
        <div className="u-stack-8 int-mt">
          {servicios.map(s => (
            <Card key={s.id} className="int-item">
              <div className="u-min0">
                <div className="u-row-center-8">
                  <span className="int-item__titulo">{s.name}</span>
                  <StatusBadge kind="neutral" caps={false}>{etiquetaInterna(t, 'criterio_', s.criterion)}</StatusBadge>
                  {!s.is_active && <StatusBadge kind="warning" caps={false}>{t('internos.inactivo')}</StatusBadge>}
                </div>
                <div className="int-sub">{[t('internos.al_mes', { importe: fmtMoneda(s.monthly_amount, { moneda: s.currency }) }), s.description].filter(Boolean).join(' · ')}</div>
              </div>
              <div className="u-row-6">
                <IconButton ariaLabel={t('internos.vista_previa')} title={t('internos.vista_previa')} onClick={() => setViendo(s)}><Eye size={14} aria-hidden /></IconButton>
                <IconButton variante="caja" ariaLabel={t('internos.editar')} title={t('internos.editar')} onClick={() => setEditando(s)}><Pencil size={14} aria-hidden /></IconButton>
                <IconButton variante="caja" tono="peligro" ariaLabel={t('internos.borrar')} title={t('internos.borrar')}
                  onClick={async () => { if (await confirmar({ message: t('internos.borrar_confirmar', { titulo: s.name }), danger: true })) borrar.mutate(s.id) }}>
                  <Trash2 size={14} aria-hidden />
                </IconButton>
              </div>
            </Card>
          ))}
        </div>
      )}
      {editando && <FormularioDeServicio item={editando === 'nuevo' ? null : editando} onClose={() => setEditando(null)} />}
      {viendo && <VistaPrevia item={viendo} onClose={() => setViendo(null)} />}
    </SeccionDeAjustes>
  )
}
