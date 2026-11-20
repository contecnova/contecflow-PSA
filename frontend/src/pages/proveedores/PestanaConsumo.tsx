/**
 * Ficha del proveedor → Consumo y facturación (19-11-2026), la parte nueva:
 *
 * 1. Consumo registrado a mano o importado (dispositivos, llamadas, gastos…);
 *    horas, tickets e hitos aceptados se miden solos.
 * 2. Previsión del periodo por contrato (todas las líneas, con mínimos, topes,
 *    escalados, créditos y bonus) y cierre del periodo → estado de cuenta.
 * 3. Estados de cuenta: conciliar con la factura del proveedor (dentro de la
 *    tolerancia queda conciliado, fuera en disputa), aprobar (segregación: no
 *    aprueba quien cerró ni quien registró la factura; 409) o disputar.
 *
 * Las facturas y la conciliación por horas de siempre las pinta la página
 * debajo de esto (`SubcontractorsPage`).
 *
 * Migración 191: si la empresa tiene un flujo de aprobación de «estado de
 * cuenta de proveedor» (motor común, por importe), «Aprobar» lo envía a la
 * bandeja (`pending_approval`) y se decide allí; disputarlo lo saca de ella.
 * Los consumos medidos en la CMDB o recibidos de otro sistema muestran su
 * origen y sus muestras (máximo, media, último).
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Calculator, CheckCircle2, Gauge, Lock, Plus, Scale, Trash2, AlertTriangle } from 'lucide-react'
import { Button, Card, EmptyState, IconButton, Input, Modal, Select, Spinner, TablaSimple, useErroresDeCampo } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { openConfirmGlobal, pedirTexto } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { proveedoresApi } from '../../services/api/proveedores'
import type { ConsumoIn, ContratoDeProveedor, EstadoDeCuenta } from '../../services/api/tipos-proveedores'
import type { SubFactura, Subcontratista } from '../../services/api/tipos-alm'
import { useCatalogo } from '../../hooks/useCatalogo'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { extractErr, fmtDate, fmtNumber } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { TONO_CUENTA, accionesDeEstado, conRespaldo, enBandeja, mesDe, numeroONull, textoONull } from './logica'
import { etiquetaDe, useProyectosActivos, usePermisosDeProveedores, useT } from './comunes'

function RegistrarConsumo({ sub, contratos, onClose }: { sub: Subcontratista; contratos: ContratoDeProveedor[]; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const campos = useErroresDeCampo()
  const unidades = useCatalogo('supplier-billing-units')
  const proyectos = useProyectosActivos()
  const mes = mesDe()
  const [f, setF] = useState({ contract_id: contratos[0]?.id || '', pricing_line_id: '', project_id: '', period_start: mes.desde, period_end: mes.hasta, unit: '', quantity: '', amount: '', description: '' })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => { campos.limpiar(k); setF(x => ({ ...x, [k]: e.target.value })) }
  const lineas = contratos.find(c => c.id === f.contract_id)?.lines || []
  const linea = lineas.find(l => l.id === f.pricing_line_id)
  useEffect(() => { if (linea?.unit) setF(x => ({ ...x, unit: linea.unit || x.unit })) }, [linea?.unit])
  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => {
      const d: ConsumoIn = {
        contract_id: f.contract_id || null, pricing_line_id: f.pricing_line_id || null, service_id: linea?.service_id || null,
        project_id: f.project_id || null, period_start: f.period_start, period_end: f.period_end, unit: f.unit || null,
        quantity: numeroONull(f.quantity) ?? 0, amount: numeroONull(f.amount), source: 'manual', description: textoONull(f.description),
      }
      return proveedoresApi.crearConsumo(sub.id, d)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); toast.success(t('proveedores.consumo_registrado')); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })
  return (
    <Modal open title={t('proveedores.registrar_consumo')} onClose={onClose} width={620}>
      <div className="u-stack-8">
        <p className="u-text2-sm">{t('proveedores.registrar_consumo_d')}</p>
        <div className="prv-rejilla">
          <Select label={t('proveedores.contrato')} value={f.contract_id} onChange={set('contract_id')} placeholder={t('proveedores.sin_contrato')}
            options={contratos.map(c => ({ value: c.id, label: c.title }))} />
          <Select label={t('proveedores.linea_de_precio')} value={f.pricing_line_id} onChange={set('pricing_line_id')} placeholder={t('proveedores.elegir')}
            options={lineas.map(l => ({ value: l.id, label: [etiquetaDe(t, 'modelo_', l.model), l.description].filter(Boolean).join(' · ') }))} />
          <Input label={t('proveedores.desde')} type="date" value={f.period_start} onChange={set('period_start')} error={campos.de('period_start')} />
          <Input label={t('proveedores.hasta')} type="date" value={f.period_end} onChange={set('period_end')} error={campos.de('period_end')} />
          <Select label={t('proveedores.unidad')} value={f.unit} onChange={set('unit')} placeholder={t('proveedores.elegir')} options={unidades.opciones} />
          <Input label={t('proveedores.cantidad')} type="number" min={0} step="any" value={f.quantity} onChange={set('quantity')} error={campos.de('quantity')} />
          <Input label={t('proveedores.importe_gasto')} hint={t('proveedores.importe_gasto_d')} type="number" min={0} step="0.01" value={f.amount} onChange={set('amount')} error={campos.de('amount')} />
          <Select label={t('subcontractors.col_proyecto')} value={f.project_id} onChange={set('project_id')} placeholder={t('proveedores.sin_proyecto')}
            options={proyectos.map(p => ({ value: p.id, label: `${p.code} — ${p.name}` }))} />
          <Input className="prv-completo" label={t('subcontractors.descripcion')} value={f.description} onChange={set('description')} error={campos.de('description')} />
        </div>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending}
            disabled={guardar.isPending || !f.period_start || !f.period_end || (!f.quantity && !f.amount)}>{t('proveedores.registrar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function Conciliar({ estado, facturas, onClose }: { estado: EstadoDeCuenta; facturas: SubFactura[]; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const fmtMoneda = useFormatoMoneda()
  const [factura, setFactura] = useState(estado.invoice_id || '')
  const conciliar = useMutation({
    mutationFn: () => proveedoresApi.conciliar(estado.id, factura),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['suppliers'] })
      qc.invalidateQueries({ queryKey: ['sub-invoices'] })
      toast.success(r.data.status === 'disputed' ? t('proveedores.conciliado_fuera') : t('proveedores.conciliado_ok'))
      onClose()
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Modal open title={t('proveedores.conciliar')} subtitle={`${estado.contract_title || ''} · ${fmtDate(estado.period_start)} – ${fmtDate(estado.period_end)}`} onClose={onClose} width={520}>
      <div className="u-stack-8">
        <p className="u-text2-sm">{t('proveedores.conciliar_d', { importe: fmtMoneda(estado.expected_amount, { moneda: estado.currency }) })}</p>
        <Select label={t('proveedores.factura')} value={factura} onChange={e => setFactura(e.target.value)} placeholder={facturas.length ? t('proveedores.elegir') : t('proveedores.sin_facturas')}
          options={facturas.map(f => ({ value: f.id, label: `${f.invoice_number} · ${fmtDate(f.issue_date)} · ${fmtMoneda(f.amount)}` }))} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => conciliar.mutate()} disabled={!factura || conciliar.isPending} loading={conciliar.isPending}>{t('proveedores.conciliar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

export default function PestanaConsumo({ sub, facturas }: { sub: Subcontratista; facturas: SubFactura[] }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const fmtMoneda = useFormatoMoneda()
  const unidades = useCatalogo('supplier-billing-units')
  const { gestionar } = usePermisosDeProveedores()
  const mes = mesDe()
  const [contratoId, setContratoId] = useState('')
  const [desde, setDesde] = useState(mes.desde)
  const [hasta, setHasta] = useState(mes.hasta)
  const [registrando, setRegistrando] = useState(false)
  const [conciliando, setConciliando] = useState<EstadoDeCuenta | null>(null)

  const { data: contratos = [], isLoading } = useQuery({ queryKey: ['suppliers', 'contracts', sub.id], queryFn: () => proveedoresApi.contratos(sub.id).then(r => r.data) })
  useEffect(() => {
    if (!contratoId && contratos.length) setContratoId((contratos.find(c => c.status === 'active') || contratos[0]).id)
  }, [contratos, contratoId])
  const { data: consumos = [] } = useQuery({ queryKey: ['suppliers', 'usage', sub.id], queryFn: () => proveedoresApi.consumos(sub.id).then(r => r.data) })
  const { data: estados = [] } = useQuery({ queryKey: ['suppliers', 'statements', sub.id], queryFn: () => proveedoresApi.estadosDeCuenta(sub.id).then(r => r.data) })
  const { data: prevision, isFetching: calculando } = useQuery({
    queryKey: ['suppliers', 'forecast', contratoId, desde, hasta],
    queryFn: () => proveedoresApi.prevision(contratoId, { desde, hasta }).then(r => r.data),
    enabled: !!contratoId && !!desde && !!hasta,
  })
  const tituloDe = (id: string | null) => contratos.find(c => c.id === id)?.title || '—'

  const alFallar = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const refrescar = () => qc.invalidateQueries({ queryKey: ['suppliers'] })
  const cerrar = useMutation({ mutationFn: () => proveedoresApi.cerrarPeriodo(contratoId, desde, hasta), onSuccess: () => { refrescar(); toast.success(t('proveedores.periodo_cerrado')) }, onError: alFallar })
  const borrarConsumo = useMutation({ mutationFn: (id: string) => proveedoresApi.borrarConsumo(id), onSuccess: refrescar, onError: alFallar })
  const aprobar = useMutation({
    mutationFn: (id: string) => proveedoresApi.aprobarEstado(id),
    onSuccess: r => {
      refrescar()
      qc.invalidateQueries({ queryKey: ['sub-invoices', sub.id] })
      toast.success(enBandeja(r.data.status) ? t('proveedores.estado_a_la_bandeja') : t('proveedores.estado_aprobado'))
    },
    onError: alFallar,
  })
  const disputar = useMutation({
    mutationFn: ({ id, motivo }: { id: string; motivo: string }) => proveedoresApi.disputarEstado(id, motivo),
    onSuccess: () => { refrescar(); toast.success(t('proveedores.estado_disputado')) },
    onError: alFallar,
  })
  const moneda = prevision?.currency || contratos.find(c => c.id === contratoId)?.currency || null
  const dinero = (n: number | null | undefined, m: string | null = moneda) => fmtMoneda(n ?? 0, { moneda: m })

  if (isLoading) return <Spinner />
  return (
    <div className="u-stack-16">
      {/* Previsión del periodo */}
      <Card className="prv-bloque">
        <div className="prv-bloque-titulo"><Calculator size={16} aria-hidden />{t('proveedores.prevision')}</div>
        {contratos.length === 0 ? <p className="u-text2-sm">{t('proveedores.prevision_sin_contrato')}</p> : (
          <>
            <div className="prv-barra">
              <div className="prv-rejilla--3 prv-rejilla u-flex1">
                <Select label={t('proveedores.contrato')} value={contratoId} placeholder={false} onChange={e => setContratoId(e.target.value)}
                  options={contratos.map(c => ({ value: c.id, label: `${c.title} · ${etiquetaDe(t, 'contrato_estado_', c.status)}` }))} />
                <Input label={t('proveedores.desde')} type="date" value={desde} onChange={e => setDesde(e.target.value)} />
                <Input label={t('proveedores.hasta')} type="date" value={hasta} onChange={e => setHasta(e.target.value)} />
              </div>
              {gestionar && (
                <Button icon={<Lock size={14} />} disabled={!prevision || cerrar.isPending} loading={cerrar.isPending}
                  onClick={() => openConfirmGlobal({ message: t('proveedores.cerrar_periodo_confirmar', { desde: fmtDate(desde), hasta: fmtDate(hasta) }), onConfirm: () => cerrar.mutate() })}>
                  {t('proveedores.cerrar_periodo')}
                </Button>
              )}
            </div>
            {calculando && !prevision ? <Spinner /> : prevision && (
              <div className="u-stack-8">
                {prevision.warnings.map((w, i) => (
                  <div key={i} className="prv-aviso"><AlertTriangle size={13} aria-hidden /> {conRespaldo(t, `proveedores.aviso_${w.code}`, w.code)}</div>
                ))}
                {prevision.lines.length === 0 ? <p className="u-text2-sm">{t('proveedores.prevision_vacia')}</p> : (
                  <div className="u-scroll-x">
                    <TablaSimple claseTabla="u-table">
                      <thead>
                        <tr className="u-border-b">
                          {[t('proveedores.modelo_de_cobro'), t('subcontractors.descripcion'), t('proveedores.cantidad'), t('proveedores.precio_unitario'), t('subcontractors.col_importe'), t('proveedores.origen')].map(h => (
                            <th key={h} scope="col" className="sub-th">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {prevision.lines.map((l, i) => (
                          <tr key={`${l.pricing_line_id ?? 'x'}-${i}`} className="sub-tr">
                            <td className="sub-td">{etiquetaDe(t, 'modelo_', l.model)}</td>
                            <td className="sub-td sub-td--muted">{l.description || '—'}</td>
                            <td className="sub-td sub-td--mono">{fmtNumber(l.quantity, 2)}{l.unit ? ` ${unidades.etiqueta(l.unit)}` : ''}</td>
                            <td className="sub-td sub-td--mono">{l.unit_price != null ? dinero(l.unit_price) : '—'}</td>
                            <td className="sub-td sub-td--mono">{dinero(l.amount)}</td>
                            <td className="sub-td sub-td--muted">{l.source ? conRespaldo(t, `proveedores.origen_${l.source}`, l.source) : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </TablaSimple>
                  </div>
                )}
                <div className="prv-datos">
                  <div className="prv-dato"><div className="prv-dato-etiqueta">{t('proveedores.subtotal')}</div><div className="prv-dato-valor prv-numero">{dinero(prevision.subtotal)}</div></div>
                  <div className="prv-dato"><div className="prv-dato-etiqueta">{t('proveedores.creditos')}</div><div className="prv-dato-valor prv-numero prv-numero--neg">{dinero(-Math.abs(prevision.credits))}</div></div>
                  <div className="prv-dato"><div className="prv-dato-etiqueta">{t('proveedores.bonus')}</div><div className="prv-dato-valor prv-numero">{dinero(prevision.bonus)}</div></div>
                  <div className="prv-dato"><div className="prv-dato-etiqueta">{t('proveedores.ajustes')}</div><div className="prv-dato-valor prv-numero">{dinero(prevision.adjustments)}</div></div>
                  <div className="prv-dato"><div className="prv-dato-etiqueta">{t('proveedores.esperado')}</div><div className="prv-dato-valor prv-titulo-item prv-numero">{dinero(prevision.expected_amount)}</div></div>
                </div>
              </div>
            )}
          </>
        )}
      </Card>

      {/* Consumo registrado */}
      <Card className="prv-bloque">
        <div className="prv-cabecera-item">
          <div className="prv-bloque-titulo"><Gauge size={16} aria-hidden />{t('proveedores.consumo')}</div>
          {gestionar && <Button size="sm" icon={<Plus size={14} />} onClick={() => setRegistrando(true)}>{t('proveedores.registrar_consumo')}</Button>}
        </div>
        {consumos.length === 0 ? <p className="u-text2-sm">{t('proveedores.sin_consumo')}</p> : (
          <div className="u-scroll-x">
            <TablaSimple claseTabla="u-table">
              <thead>
                <tr className="u-border-b">
                  {[t('externos.col_periodo'), t('proveedores.contrato'), t('proveedores.cantidad'), t('subcontractors.col_importe'), t('subcontractors.descripcion'), t('proveedores.origen')].map(h => (
                    <th key={h} scope="col" className="sub-th">{h}</th>
                  ))}
                  <th scope="col" className="sub-th"><span className="u-sr-only">{t('subcontractors.col_acciones')}</span></th>
                </tr>
              </thead>
              <tbody>
                {consumos.map(u => (
                  <tr key={u.id} className="sub-tr">
                    <td className="sub-td sub-td--muted">{fmtDate(u.period_start)} – {fmtDate(u.period_end)}</td>
                    <td className="sub-td">{tituloDe(u.contract_id)}</td>
                    <td className="sub-td sub-td--mono">{fmtNumber(u.quantity, 2)}{u.unit ? ` ${unidades.etiqueta(u.unit)}` : ''}</td>
                    <td className="sub-td sub-td--mono">{u.amount != null ? fmtMoneda(u.amount) : '—'}</td>
                    <td className="sub-td sub-td--muted">{u.description || '—'}</td>
                    <td className="sub-td">
                      {etiquetaDe(t, 'origen_', u.source)}{u.source_system ? ` · ${u.source_system}` : ''}
                      {u.detail?.samples?.length ? (
                        <div className="u-text3-xs">{t('proveedores.muestras_resumen', {
                          n: u.detail.samples.length, max: fmtNumber(u.detail.max ?? 0, 0), media: fmtNumber(u.detail.average ?? 0, 1),
                          agregacion: etiquetaDe(t, 'agregacion_', u.detail.aggregation || 'last'),
                        })}</div>
                      ) : null}
                    </td>
                    <td className="sub-td">
                      {gestionar && !u.statement_id && (
                        <IconButton className="sub-borrar" onClick={() => openConfirmGlobal({ message: t('proveedores.borrar_consumo_confirmar'), danger: true, onConfirm: () => borrarConsumo.mutate(u.id) })}
                          ariaLabel={t('proveedores.borrar_consumo')} title={t('proveedores.borrar_consumo')}><Trash2 size={14} aria-hidden /></IconButton>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </TablaSimple>
          </div>
        )}
      </Card>

      {/* Estados de cuenta */}
      <Card className="prv-bloque">
        <div className="prv-bloque-titulo"><Scale size={16} aria-hidden />{t('proveedores.estados_de_cuenta')}</div>
        <p className="u-text3-xs">{t('proveedores.estados_de_cuenta_d')}</p>
        {estados.length === 0 ? (
          <EmptyState icon={<Scale size={28} />} title={t('proveedores.sin_estados')} description={t('proveedores.sin_estados_d')} />
        ) : (
          <div className="u-scroll-x prv-mt">
            <TablaSimple claseTabla="u-table">
              <thead>
                <tr className="u-border-b">
                  {[t('proveedores.contrato'), t('externos.col_periodo'), t('proveedores.esperado'), t('proveedores.factura'), t('externos.col_diferencia'), t('subcontractors.col_estado')].map(h => (
                    <th key={h} scope="col" className="sub-th">{h}</th>
                  ))}
                  <th scope="col" className="sub-th"><span className="u-sr-only">{t('subcontractors.col_acciones')}</span></th>
                </tr>
              </thead>
              <tbody>
                {estados.map(s => {
                  const signo = (s.difference ?? 0) > 0 ? '+' : ''
                  return (
                    <tr key={s.id} className="sub-tr">
                      <td className="sub-td sub-td--strong">{s.contract_title || tituloDe(s.contract_id)}</td>
                      <td className="sub-td sub-td--muted">{fmtDate(s.period_start)} – {fmtDate(s.period_end)}</td>
                      <td className="sub-td sub-td--mono">{fmtMoneda(s.expected_amount, { moneda: s.currency })}</td>
                      <td className="sub-td sub-td--mono">{s.invoice_amount != null ? fmtMoneda(s.invoice_amount, { moneda: s.currency }) : '—'}</td>
                      <td className={`sub-td sub-td--mono${(s.difference ?? 0) > 0 ? ' prv-numero--neg' : ''}`}>
                        {s.difference != null ? `${signo}${fmtMoneda(s.difference, { moneda: s.currency })}` : '—'}
                        {s.difference_pct != null && <span className="u-text2-xs"> ({signo}{fmtNumber(s.difference_pct, 1)}%)</span>}
                      </td>
                      <td className="sub-td">
                        <StatusBadge kind={TONO_CUENTA[s.status] || 'neutral'} caps={false}>{etiquetaDe(t, 'cuenta_estado_', s.status)}</StatusBadge>
                        {s.dispute_reason && <div className="u-text3-xs">{conRespaldo(t, `proveedores.motivo_${s.dispute_reason}`, s.dispute_reason)}</div>}
                        {enBandeja(s.status) && <div className="u-text3-xs"><Link to="/approvals">{t('proveedores.ver_en_la_bandeja')}</Link></div>}
                      </td>
                      <td className="sub-td">
                        {gestionar && accionesDeEstado(s.status, !!s.invoice_id).length > 0 && (
                          <div className="u-row-6">
                            {accionesDeEstado(s.status, !!s.invoice_id).includes('reconcile') && (
                              <Button size="xs" variant="secondary" onClick={() => setConciliando(s)}>{t('proveedores.conciliar')}</Button>
                            )}
                            {accionesDeEstado(s.status, !!s.invoice_id).includes('approve') && (
                              <Button size="xs" icon={<CheckCircle2 size={13} />}
                                onClick={() => openConfirmGlobal({ message: t('proveedores.aprobar_estado_confirmar'), onConfirm: () => aprobar.mutate(s.id) })}>
                                {t('subcontractors.approve')}
                              </Button>
                            )}
                            {accionesDeEstado(s.status, !!s.invoice_id).includes('dispute') && (
                              <Button size="xs" variant="ghost" className="sub-borrar"
                                onClick={async () => {
                                  const motivo = await pedirTexto({ message: t('proveedores.disputar_estado'), label: t('proveedores.motivo'), required: true, multiline: true, danger: true })
                                  if (motivo) disputar.mutate({ id: s.id, motivo })
                                }}>{t('proveedores.disputar')}</Button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </TablaSimple>
          </div>
        )}
      </Card>

      {registrando && <RegistrarConsumo sub={sub} contratos={contratos} onClose={() => setRegistrando(false)} />}
      {conciliando && <Conciliar estado={conciliando} facturas={facturas} onClose={() => setConciliando(null)} />}
    </div>
  )
}
