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
import type { CSSProperties } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Plus, Trash2 } from 'lucide-react'
import { invoicesApi } from '../../services/api'
import { Button, Modal, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr, localeActivo } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'

type Linea = { description: string; quantity: number; unit: string; unit_price: number; discount_pct: number; amount?: number; source_type?: string | null; source_ids?: unknown }
type Factura = {
  id: string; number: string; status: string; client_name?: string; client_email?: string; client_vat?: string; client_address?: string
  issue_date?: string; due_date?: string; paid_date?: string; tax_rate?: number; currency?: string; notes?: string; po_reference?: string
  period_from?: string; period_to?: string; subtotal?: number; tax_amount?: number; total?: number; project_code?: string; project_name?: string
  lines?: Linea[]
}
const CABECERA = ['client_name', 'client_vat', 'client_email', 'client_address', 'issue_date', 'due_date', 'po_reference', 'notes'] as const

const dinero = (n: number | undefined, moneda = 'EUR') =>
  (n ?? 0).toLocaleString(localeActivo(), { style: 'currency', currency: moneda || 'EUR' })
const importe = (l: Linea) => Math.round((Number(l.quantity) || 0) * (Number(l.unit_price) || 0) * (1 - (Number(l.discount_pct) || 0) / 100) * 100) / 100

export default function FichaDeFactura({ id, onClose, onPdf, onEstado, etiquetaDeEstado }: {
  id: string; onClose: () => void; onPdf: () => void; onEstado: (status: string) => void
  etiquetaDeEstado: (status: string) => { label: string; color: string }
}) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: f, isLoading } = useQuery<Factura>({ queryKey: ['invoice', id], queryFn: () => invoicesApi.get(id).then(r => r.data as Factura) })
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
  const campo: CSSProperties = { background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '6px 9px', color: 'var(--text-1)', fontFamily: 'inherit', fontSize: 'var(--text-sm)', width: '100%', boxSizing: 'border-box' }
  const etiqueta: CSSProperties = { fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 3 }
  if (isLoading || !f) return <Modal open onClose={onClose} title="…" size="lg"><Spinner /></Modal>
  const borrador = f.status === 'draft'
  const estado = etiquetaDeEstado(f.status)
  const subtotal = editando ? lineas.reduce((a, l) => a + importe(l), 0) : (f.subtotal ?? 0)
  const impuestos = editando ? Math.round(subtotal * (Number(form.tax_rate) || 0)) / 100 : (f.tax_amount ?? 0)
  const total = editando ? Math.round((subtotal + impuestos) * 100) / 100 : (f.total ?? 0)
  return (
    <Modal open onClose={onClose} size="xl"
      title={<span className="u-row-center-10">
        <span style={{ fontFamily: 'var(--font-mono)' }}>{f.number}</span>
        <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, padding: '2px 8px', borderRadius: 20, color: estado.color, border: `1px solid ${estado.color}` }}>{estado.label}</span>
      </span>}>
      <div style={{ display: 'grid', gap: 16 }}>
        {!borrador && <div role="status" className="u-text2-sm">{t('invoices.ficha_emitida')}</div>}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
          {CABECERA.filter(c => c !== 'notes' && c !== 'client_address').map(c => (
            <label key={c}>
              <div style={etiqueta}>{t(`invoices.campo_${c}`)}</div>
              {editando
                ? <input aria-label={t(`invoices.campo_${c}`)} type={c.endsWith('_date') ? 'date' : 'text'} value={String(form[c] ?? '')} onChange={e => setForm(v => ({ ...v, [c]: e.target.value }))} style={campo} />
                : <div className="u-sm">{(f[c] as string) || '—'}</div>}
            </label>
          ))}
          <div>
            <div style={etiqueta}>{t('invoices.project')}</div>
            <div className="u-sm">{f.project_code ? `${f.project_code} · ${f.project_name ?? ''}` : '—'}</div>
          </div>
          <div>
            <div style={etiqueta}>{t('invoices.ficha_periodo')}</div>
            <div className="u-sm">{f.period_from ? `${f.period_from} → ${f.period_to ?? ''}` : '—'}</div>
          </div>
        </div>
        <label>
          <div style={etiqueta}>{t('invoices.campo_client_address')}</div>
          {editando ? <textarea aria-label={t('invoices.campo_client_address')} value={String(form.client_address ?? '')} onChange={e => setForm(v => ({ ...v, client_address: e.target.value }))} rows={2} style={campo} />
            : <div style={{ fontSize: 'var(--text-sm)', whiteSpace: 'pre-wrap' }}>{f.client_address || '—'}</div>}
        </label>

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
          <thead><tr style={{ textAlign: 'left', color: 'var(--text-3)', fontSize: 'var(--text-xs)', textTransform: 'uppercase' }}>
            <th style={{ padding: 6 }}>{t('invoices.ficha_concepto')}</th><th style={{ padding: 6, width: 80 }}>{t('invoices.ficha_cantidad')}</th>
            <th style={{ padding: 6, width: 70 }}>{t('invoices.ficha_unidad')}</th><th style={{ padding: 6, width: 110 }}>{t('invoices.ficha_precio')}</th>
            <th style={{ padding: 6, width: 80 }}>{t('invoices.ficha_descuento')}</th><th style={{ padding: 6, width: 110, textAlign: 'right' }}>{t('invoices.ficha_importe')}</th>
            {editando && <th style={{ width: 30 }} aria-label={t('invoices.ficha_quitar_linea')} />}
          </tr></thead>
          <tbody>
            {(editando ? lineas : f.lines || []).map((l, i) => (
              <tr key={i} style={{ borderTop: '1px solid var(--surface-4)' }}>
                {editando ? (<>
                  <td style={{ padding: 4 }}><input aria-label={t('invoices.ficha_concepto')} value={l.description} onChange={e => setLineas(v => v.map((x, j) => j === i ? { ...x, description: e.target.value } : x))} style={campo} /></td>
                  {(['quantity', 'unit', 'unit_price', 'discount_pct'] as const).map(k => (
                    <td key={k} style={{ padding: 4 }}><input aria-label={t(`invoices.ficha_${k === 'quantity' ? 'cantidad' : k === 'unit' ? 'unidad' : k === 'unit_price' ? 'precio' : 'descuento'}`)}
                      type={k === 'unit' ? 'text' : 'number'} value={String(l[k] ?? '')} onChange={e => setLineas(v => v.map((x, j) => j === i ? { ...x, [k]: e.target.value } : x))} style={campo} /></td>
                  ))}
                  <td style={{ padding: 6, textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{dinero(importe(l), f.currency)}</td>
                  <td><button type="button" aria-label={t('invoices.ficha_quitar_linea')} onClick={() => setLineas(v => v.filter((_, j) => j !== i))}
                    style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer' }}><Trash2 size={13} /></button></td>
                </>) : (<>
                  <td style={{ padding: 6 }}>{l.description}</td><td style={{ padding: 6 }}>{l.quantity}</td><td style={{ padding: 6 }}>{l.unit}</td>
                  <td style={{ padding: 6, fontFamily: 'var(--font-mono)' }}>{dinero(l.unit_price, f.currency)}</td><td style={{ padding: 6 }}>{l.discount_pct ? `${l.discount_pct}%` : '—'}</td>
                  <td style={{ padding: 6, textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{dinero(l.amount, f.currency)}</td>
                </>)}
              </tr>
            ))}
          </tbody>
        </table>
        {editando && (
          <button type="button" onClick={() => setLineas(v => [...v, { description: '', quantity: 1, unit: 'h', unit_price: 0, discount_pct: 0 }])}
            style={{ justifySelf: 'start', display: 'flex', alignItems: 'center', gap: 5, background: 'none', border: '1px dashed var(--surface-5)', borderRadius: 7, padding: '5px 10px', color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-sm)' }}>
            <Plus size={13} /> {t('invoices.ficha_anadir_linea')}
          </button>
        )}
        <div style={{ justifySelf: 'end', display: 'grid', gridTemplateColumns: 'auto auto', gap: '4px 18px', fontSize: 'var(--text-sm)' }}>
          <span className="u-text3">{t('invoices.ficha_subtotal')}</span><span style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{dinero(subtotal, f.currency)}</span>
          <span className="u-text3">
            {t('invoices.ficha_impuestos')} {editando
              ? <input aria-label={t('invoices.ficha_impuestos')} type="number" value={String(form.tax_rate ?? 0)} onChange={e => setForm(v => ({ ...v, tax_rate: e.target.value }))} style={{ ...campo, width: 70, display: 'inline-block' }} />
              : `(${f.tax_rate ?? 0}%)`}
          </span><span style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{dinero(impuestos, f.currency)}</span>
          <strong>{t('invoices.total')}</strong><strong style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{dinero(total, f.currency)}</strong>
        </div>
        <label>
          <div style={etiqueta}>{t('invoices.campo_notes')}</div>
          {editando ? <textarea aria-label={t('invoices.campo_notes')} value={String(form.notes ?? '')} onChange={e => setForm(v => ({ ...v, notes: e.target.value }))} rows={2} style={campo} />
            : <div style={{ fontSize: 'var(--text-sm)', whiteSpace: 'pre-wrap', color: 'var(--text-2)' }}>{f.notes || '—'}</div>}
        </label>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', borderTop: '1px solid var(--surface-4)', paddingTop: 12 }}>
          {editando ? (<>
            <Button onClick={guardar} disabled={guardando}>{guardando ? '…' : t('invoices.ficha_guardar')}</Button>
            <Button variant="secondary" onClick={() => { setEditando(false); setLineas((f.lines || []).map(l => ({ ...l }))) }}>{t('invoices.cancel')}</Button>
          </>) : (<>
            {borrador && <Button onClick={() => setEditando(true)}>{t('invoices.ficha_editar')}</Button>}
            {borrador && <Button variant="secondary" onClick={() => onEstado('sent')}>{t('invoices.send')}</Button>}
            {(f.status === 'sent' || f.status === 'overdue') && <Button variant="secondary" onClick={() => onEstado('paid')}>{t('invoices.paid')}</Button>}
            {['draft', 'sent', 'overdue'].includes(f.status) && <Button variant="ghost" onClick={() => onEstado('cancelled')}>{t('invoices.ficha_anular')}</Button>}
            <Button variant="secondary" onClick={onPdf}><Download size={13} /> {t('invoices.download_pdf')}</Button>
            {borrador && <Button variant="danger" onClick={borrar}><Trash2 size={13} /> {t('invoices.ficha_borrar')}</Button>}
          </>)}
        </div>
      </div>
    </Modal>
  )
}
