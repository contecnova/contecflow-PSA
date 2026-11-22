/**
 * Ficha de una factura (revisión 2026-11).
 *
 * La pantalla de facturación sólo dejaba enviar, marcar como pagada y bajar el
 * PDF: no se podía abrir una factura ni corregir un borrador. Aquí se ve entera
 * y, si es BORRADOR, se edita (cabecera y líneas) o se borra. Una factura
 * enviada no se modifica: el servidor lo rechaza (409) y la ficha lo explica.
 * Los importes los calcula el servidor; aquí sólo se adelanta el total.
 */
import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Plus, Trash2 } from 'lucide-react'
import { invoicesApi } from '../../services/api'
import type { Factura, LineaDeFactura } from '../../services/api/tipos-finanzas'
import { Button, IconButton, Modal, Spinner, StatusBadge, TablaSimple, Input, Textarea } from '../ui'
import DateInput from '../ui/DateInput'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr, fmtDate, formatearMoneda } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'

import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { redondear2 } from '../../utils/redondeo'
import './FichaDeFactura.css'
/** Línea del formulario: la de la ficha (InvoiceLineOut) o una nueva, sin id ni importe. `source_ids` se reenvía tal cual
 *  para que el servidor no libere las horas facturadas al guardar. */
type Linea = Pick<LineaDeFactura, 'description' | 'quantity' | 'unit' | 'unit_price' | 'discount_pct'>
  & Partial<Pick<LineaDeFactura, 'amount' | 'source_type' | 'source_ids'>>
const CABECERA = ['client_name', 'client_vat', 'client_email', 'client_address', 'issue_date', 'due_date', 'po_reference', 'notes'] as const

const dinero = (n: number | undefined, moneda: string) => formatearMoneda(n ?? 0, moneda)
const importe = (l: Linea) => Math.round((Number(l.quantity) || 0) * (Number(l.unit_price) || 0) * (1 - (Number(l.discount_pct) || 0) / 100) * 100) / 100

export default function FichaDeFactura({ id, onClose, onPdf, onEstado, etiquetaDeEstado }: {
  id: string; onClose: () => void; onPdf: () => void; onEstado: (status: string) => void
  etiquetaDeEstado: (status: string) => { label: string; color: string }
}) {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: f, isLoading } = useQuery<Factura>({ queryKey: ['invoice', id], queryFn: () => invoicesApi.get(id).then(r => r.data) })
  const [editando, setEditando] = useState(false)
  const [form, setForm] = useState<Record<string, string | number>>({})
  const [lineas, setLineas] = useState<Linea[]>([])
  const [guardando, setGuardando] = useState(false)
  useEffect(() => {
    if (!f) return
    setForm({ ...Object.fromEntries(CABECERA.map(c => [c, (f[c] as string) || ''])), tax_rate: f.tax_rate ?? 0 })
    setLineas((f.lines || []).map(l => ({ ...l })))
  }, [f])
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['invoice', id] }); qc.invalidateQueries({ queryKey: ['invoices'] }); qc.invalidateQueries({ queryKey: ['invoice-summary'] }) }
  const guardar = async () => {
    setGuardando(true)
    try {
      const cabecera = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === '' ? null : v]))
      await invoicesApi.update(id, { ...cabecera, tax_rate: Number(form.tax_rate) || 0,
        lines: lineas.map(({ amount: _a, ...l }) => ({ ...l, quantity: Number(l.quantity) || 0, unit_price: Number(l.unit_price) || 0, discount_pct: Number(l.discount_pct) || 0 })) })
      toast.success(t('invoices.ficha_guardada')); setEditando(false); refrescar()
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setGuardando(false) }
  }
  const borrar = () => openConfirmGlobal({
    message: t('invoices.ficha_borrar_confirmar', { numero: f?.number ?? '' }), danger: true,
    onConfirm: async () => {
      try { await invoicesApi.remove(id); toast.success(t('invoices.ficha_borrada')); refrescar(); onClose() }
      catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
    },
  })
  if (isLoading || !f) return <Modal open onClose={onClose} title={t('invoices.ficha_abrir')} size="lg"><Spinner /></Modal>
  const borrador = f.status === 'draft'
  const estado = etiquetaDeEstado(f.status)
  const subtotal = editando ? lineas.reduce((a, l) => a + importe(l), 0) : (f.subtotal ?? 0)
  const impuestos = editando ? redondear2(subtotal * (Number(form.tax_rate) || 0) / 100) : (f.tax_amount ?? 0) // 18-11-2026: vista previa al editar, mismo redondeo que el backend; al guardar manda el servidor
  const total = editando ? redondear2(subtotal + impuestos) : (f.total ?? 0)
  return (
    <Modal open onClose={onClose} size="xl"
      title={<span className="u-row-center-10">
        <span className="u-mono">{f.number}</span>
        <StatusBadge color={estado.color} caps={false}>{estado.label}</StatusBadge>
      </span>}>
      <div className="fidefa-grid-1">
        {!borrador && <div role="status" className="u-text2-sm">{t('invoices.ficha_emitida')}</div>}
        <div className="fidefa-grid-2">
          {CABECERA.filter(c => c !== 'notes' && c !== 'client_address').map(c => (
            <label key={c}>
              <div className="fidefa-etiqueta">{t(`invoices.campo_${c}`)}</div>
              {editando
                ? (c.endsWith('_date')
                  ? <DateInput aria-label={t(`invoices.campo_${c}`)} value={String(form[c] ?? '')} onChange={e => setForm(v => ({ ...v, [c]: e.target.value }))} className="fidefa-campo" />
                  : <Input aria-label={t(`invoices.campo_${c}`)} type="text" value={String(form[c] ?? '')} onChange={e => setForm(v => ({ ...v, [c]: e.target.value }))} inputClassName="fidefa-campo" />)
                : <div className="u-sm">{c.endsWith('_date') ? fmtDate(f[c] as string) : ((f[c] as string) || '—')}</div>}
            </label>
          ))}
          <div>
            <div className="fidefa-etiqueta">{t('invoices.project')}</div>
            <div className="u-sm">{f.project_code ? `${f.project_code} · ${f.project_name ?? ''}` : '—'}</div>
          </div>
          <div>
            <div className="fidefa-etiqueta">{t('invoices.ficha_periodo')}</div>
            <div className="u-sm">{f.period_from ? `${fmtDate(f.period_from)} – ${f.period_to ? fmtDate(f.period_to) : ''}` : '—'}</div>
          </div>
        </div>
        <label>
          <div className="fidefa-etiqueta">{t('invoices.campo_client_address')}</div>
          {editando ? <Textarea aria-label={t('invoices.campo_client_address')} value={String(form.client_address ?? '')} onChange={e => setForm(v => ({ ...v, client_address: e.target.value }))} rows={2} inputClassName="fidefa-campo" />
            : <div className="fidefa-txt-1">{f.client_address || '—'}</div>}
        </label>

        <TablaSimple claseTabla="u-table-sm">
          <thead><tr className="fidefa-txt-2">
            <th className="fidefa-sp-1">{t('invoices.ficha_concepto')}</th><th className="fidefa-box-1">{t('invoices.ficha_cantidad')}</th>
            <th className="fidefa-box-2">{t('invoices.ficha_unidad')}</th><th className="fidefa-box-3">{t('invoices.ficha_precio')}</th>
            <th className="fidefa-box-1">{t('invoices.ficha_descuento')}</th><th className="fidefa-box-4">{t('invoices.ficha_importe')}</th>
            {editando && <th className="fidefa-box-5" aria-label={t('invoices.ficha_quitar_linea')} />}
          </tr></thead>
          <tbody>
            {(editando ? lineas : f.lines || []).map((l, i) => (
              <tr key={i} className="fidefa-box-6">
                {editando ? (<>
                  <td className="fidefa-sp-2"><Input aria-label={t('invoices.ficha_concepto')} value={l.description} onChange={e => setLineas(v => v.map((x, j) => j === i ? { ...x, description: e.target.value } : x))} inputClassName="fidefa-campo" /></td>
                  {(['quantity', 'unit', 'unit_price', 'discount_pct'] as const).map(k => (
                    <td key={k} className="fidefa-sp-2"><input aria-label={t(`invoices.ficha_${k === 'quantity' ? 'cantidad' : k === 'unit' ? 'unidad' : k === 'unit_price' ? 'precio' : 'descuento'}`)}
                      type={k === 'unit' ? 'text' : 'number'} value={String(l[k] ?? '')} onChange={e => setLineas(v => v.map((x, j) => j === i ? { ...x, [k]: e.target.value } : x))} className="fidefa-campo" /></td>
                  ))}
                  <td className="fidefa-box-7">{dinero(importe(l), f.currency || fmtMoneda.moneda)}</td>
                  <td><IconButton ariaLabel={t('invoices.ficha_quitar_linea')} onClick={() => setLineas(v => v.filter((_, j) => j !== i))}
                    className="fidefa-box-8"><Trash2 size={14} /></IconButton></td>
                </>) : (<>
                  <td className="fidefa-sp-1">{l.description}</td><td className="fidefa-sp-1">{l.quantity}</td><td className="fidefa-sp-1">{l.unit}</td>
                  <td className="fidefa-box-9">{dinero(l.unit_price, f.currency || fmtMoneda.moneda)}</td><td className="fidefa-sp-1">{l.discount_pct ? `${l.discount_pct}%` : '—'}</td>
                  <td className="fidefa-box-7">{dinero(l.amount, f.currency || fmtMoneda.moneda)}</td>
                </>)}
              </tr>
            ))}
          </tbody>
        </TablaSimple>
        {editando && (
          <div>
            <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => setLineas(v => [...v, { description: '', quantity: 1, unit: 'h', unit_price: 0, discount_pct: 0 }])}>
              {t('invoices.ficha_anadir_linea')}
            </Button>
          </div>
        )}
        <div className="fidefa-grid-3">
          <span className="u-text3">{t('invoices.ficha_subtotal')}</span><span className="fidefa-txt-3">{dinero(subtotal, f.currency || fmtMoneda.moneda)}</span>
          <span className="u-text3">
            {t('invoices.ficha_impuestos')} {editando
              ? <input aria-label={t('invoices.ficha_impuestos')} type="number" value={String(form.tax_rate ?? 0)} onChange={e => setForm(v => ({ ...v, tax_rate: e.target.value }))} className="fidefa-campo2" />
              : `(${f.tax_rate ?? 0}%)`}
          </span><span className="fidefa-txt-3">{dinero(impuestos, f.currency || fmtMoneda.moneda)}</span>
          <strong>{t('invoices.total')}</strong><strong className="fidefa-txt-3">{dinero(total, f.currency || fmtMoneda.moneda)}</strong>
        </div>
        <label>
          <div className="fidefa-etiqueta">{t('invoices.campo_notes')}</div>
          {editando ? <Textarea aria-label={t('invoices.campo_notes')} value={String(form.notes ?? '')} onChange={e => setForm(v => ({ ...v, notes: e.target.value }))} rows={2} inputClassName="fidefa-campo" />
            : <div className="fidefa-txt-4">{f.notes || '—'}</div>}
        </label>
        <div className="fidefa-row-2">
          {editando ? (<>
            <Button onClick={guardar} loading={guardando}>{t('invoices.ficha_guardar')}</Button>
            <Button variant="secondary" onClick={() => { setEditando(false); setLineas((f.lines || []).map(l => ({ ...l }))) }}>{t('invoices.cancel')}</Button>
          </>) : (<>
            {borrador && <Button onClick={() => setEditando(true)}>{t('invoices.ficha_editar')}</Button>}
            {borrador && <Button variant="secondary" onClick={() => onEstado('sent')}>{t('invoices.send')}</Button>}
            {(f.status === 'sent' || f.status === 'overdue') && <Button variant="secondary" onClick={() => onEstado('paid')}>{t('invoices.paid')}</Button>}
            {['draft', 'sent', 'overdue'].includes(f.status) && <Button variant="ghost" onClick={() => onEstado('cancelled')}>{t('invoices.ficha_anular')}</Button>}
            <Button variant="secondary" icon={<Download size={14} />} onClick={onPdf}>{t('invoices.download_pdf')}</Button>
            {borrador && <Button variant="danger" icon={<Trash2 size={14} />} onClick={borrar}>{t('invoices.ficha_borrar')}</Button>}
          </>)}
        </div>
      </div>
    </Modal>
  )
}
