/**
 * Conciliación contrato ↔ factura de proveedor ↔ gasto (fase 3).
 *
 * Cada factura se compara con lo que el contrato dice que cuesta su periodo y
 * con el gasto que la paga (categoría de software o hardware). Las
 * discrepancias salen con su motivo; una revisada se acepta con nota. Arriba,
 * los periodos de facturación de contratos activos que aún no tienen factura.
 */
import { useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileWarning, Link2, Plus, RefreshCw, Trash2, Unlink } from 'lucide-react'
import { Button, EmptyState, Modal, Section, Spinner, Select } from '../../components/ui'
import Pagination from '../../components/ui/Pagination'
import DateInput from '../../components/ui/DateInput'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { almExtApi, vendorsApi } from '../../services/api'
import { almApi } from '../../services/api/alm'
import type { FacturaDeProveedor } from '../../services/api/alm'
import { fmtCurrency, fmtDate } from '../../utils/helpers'
import { EstadoAlm, errorAlm, hoyIso } from '../../components/alm/almFases'

const POR_PAGINA = 20
const CLAVES = ['alm-invoices', 'alm-costs']

function NuevaFactura({ factura, onClose }: { factura?: FacturaDeProveedor | null; onClose: () => void }) {
  const t = useAppT()
  const id = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const { data: contratos = [] } = useQuery({ queryKey: ['alm-contracts', 'todos'], queryFn: () => almExtApi.contracts().then(r => r.data ?? []) })
  const { data: proveedores = [] } = useQuery({ queryKey: ['alm-vendors'], queryFn: () => vendorsApi.list(undefined).then(r => r.data) })
  const [f, setF] = useState({
    number: factura?.number ?? '', vendor_id: factura?.vendor_id ?? '', contract_id: factura?.contract_id ?? '',
    issue_date: factura?.issue_date ?? hoyIso(), period_from: factura?.period_from ?? '', period_to: factura?.period_to ?? '',
    amount: factura?.amount?.toString() ?? '', tax_amount: factura?.tax_amount?.toString() ?? '', currency: factura?.currency ?? '',
    notes: factura?.notes ?? '',
  })
  const [error, setError] = useState('')
  const campo = (k: keyof typeof f) => (e: { target: { value: string } }) => setF(v => ({ ...v, [k]: e.target.value }))
  const { mutate, isPending } = useMutation({
    mutationFn: () => {
      const cuerpo = { ...f, vendor_id: f.vendor_id || null, contract_id: f.contract_id || null, currency: f.currency || null }
      return factura ? almApi.editarFactura(factura.id, cuerpo) : almApi.crearFactura(cuerpo)
    },
    onSuccess: () => { toast.success(t('alm.invoice_saved')); CLAVES.forEach(k => qc.invalidateQueries({ queryKey: [k] })); onClose() },
    onError: e => setError(errorAlm(t, e)),
  })
  return (
    <Modal open onClose={onClose} width={680} title={factura ? t('alm.invoice_edit') : t('alm.invoice_new')}>
      <div className="almf-rejilla-2">
        <div><label className="alm-label" htmlFor={`${id}-n`}>{t('alm.invoice_number')} *</label>
          <input id={`${id}-n`} className="alm-input" value={f.number} onChange={campo('number')} /></div>
        <div><label className="alm-label" htmlFor={`${id}-d`}>{t('alm.invoice_date')} *</label>
          <DateInput id={`${id}-d`} className="alm-input" value={f.issue_date} onChange={campo('issue_date')} /></div>
        <div><label className="alm-label" htmlFor={`${id}-c`}>{t('alm.licenses_label_contract')}</label>
          <Select suelto placeholder={false} id={`${id}-c`} className="alm-input" value={f.contract_id} onChange={campo('contract_id')}>
            <option value="">{t('alm.licenses_none_contract')}</option>
            {contratos.map(c => <option key={c.id} value={c.id}>{c.title}{c.vendor_name ? ` · ${c.vendor_name}` : ''}</option>)}
          </Select></div>
        <div><label className="alm-label" htmlFor={`${id}-v`}>{t('alm.licenses_label_vendor')}</label>
          <Select suelto placeholder={false} id={`${id}-v`} className="alm-input" value={f.vendor_id} onChange={campo('vendor_id')}>
            <option value="">{t('alm.vendor_from_contract')}</option>
            {proveedores.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
          </Select></div>
        <div><label className="alm-label" htmlFor={`${id}-pf`}>{t('alm.period_from')}</label>
          <DateInput id={`${id}-pf`} className="alm-input" value={f.period_from} onChange={campo('period_from')} /></div>
        <div><label className="alm-label" htmlFor={`${id}-pt`}>{t('alm.period_to')}</label>
          <DateInput id={`${id}-pt`} className="alm-input" value={f.period_to} onChange={campo('period_to')} /></div>
        <div><label className="alm-label" htmlFor={`${id}-a`}>{t('alm.invoice_amount')} *</label>
          <input id={`${id}-a`} type="number" min={0} step="0.01" className="alm-input" value={f.amount} onChange={campo('amount')} /></div>
        <div><label className="alm-label" htmlFor={`${id}-t`}>{t('alm.invoice_tax')}</label>
          <input id={`${id}-t`} type="number" min={0} step="0.01" className="alm-input" value={f.tax_amount} onChange={campo('tax_amount')} /></div>
        <div><label className="alm-label" htmlFor={`${id}-cur`}>{t('alm.cost_centers_label_currency')}</label>
          <input id={`${id}-cur`} maxLength={3} className="alm-input" value={f.currency} onChange={campo('currency')} placeholder={t('alm.currency_from_contract')} /></div>
        <div className="almf-col-completa"><label className="alm-label" htmlFor={`${id}-no`}>{t('alm.contracts_label_notes')}</label>
          <textarea id={`${id}-no`} rows={2} className="alm-input" value={f.notes} onChange={campo('notes')} /></div>
      </div>
      {error && <p className="u-field-error" role="alert">{error}</p>}
      <div className="almf-acciones-modal">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => mutate()} loading={isPending} disabled={isPending || !f.number || !f.amount || !f.issue_date}>{t('common.save')}</Button>
      </div>
    </Modal>
  )
}

function EnlazarGasto({ factura, onClose }: { factura: FacturaDeProveedor; onClose: () => void }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { data = [], isLoading } = useQuery({ queryKey: ['alm-invoices', factura.id, 'cand'], queryFn: () => almApi.candidatos(factura.id) })
  const { mutate, isPending } = useMutation({
    mutationFn: (gasto: string | null) => almApi.enlazarGasto(factura.id, gasto),
    onSuccess: () => { CLAVES.forEach(k => qc.invalidateQueries({ queryKey: [k] })); onClose() },
    onError: e => toast.error(errorAlm(t, e)),
  })
  return (
    <Modal open onClose={onClose} width={640} title={t('alm.invoice_link_expense', { number: factura.number })}
      subtitle={t('alm.invoice_link_hint')}>
      {isLoading ? <Spinner /> : data.length === 0 ? <p className="almf-vacio">{t('alm.invoice_no_candidates')}</p> : (
        <ul className="almf-lista">
          {data.map(g => (
            <li key={g.id} className="almf-fila">
              <div className="almf-fila__principal">
                <span className="almf-fila__nombre">{g.code} · {g.description}</span>
                <span className="almf-fila__meta">
                  <span className="almf-importe">{fmtCurrency(g.amount, g.currency)}</span>
                  <span>{fmtDate(g.expense_date)}</span>
                  <span>{t(`gastos.categoria_${g.category}`, g.category)}</span>
                  <span>{t(`alm.expense_status_${g.status}`, g.status)}</span>
                </span>
              </div>
              <Button size="sm" icon={<Link2 size={14} />} disabled={isPending} onClick={() => mutate(g.id)}>{t('alm.invoice_link')}</Button>
            </li>
          ))}
        </ul>
      )}
      <div className="almf-acciones-modal">
        {factura.expense_id && <Button variant="ghost" icon={<Unlink size={14} />} onClick={() => mutate(null)}>{t('alm.invoice_unlink')}</Button>}
        <Button variant="secondary" onClick={onClose}>{t('common.close')}</Button>
      </div>
    </Modal>
  )
}

function AceptarDiscrepancia({ factura, onClose }: { factura: FacturaDeProveedor; onClose: () => void }) {
  const t = useAppT()
  const qc = useQueryClient()
  const [nota, setNota] = useState('')
  const [error, setError] = useState('')
  const { mutate, isPending } = useMutation({
    mutationFn: () => almApi.aceptarFactura(factura.id, nota),
    onSuccess: () => { CLAVES.forEach(k => qc.invalidateQueries({ queryKey: [k] })); onClose() },
    onError: e => setError(errorAlm(t, e)),
  })
  return (
    <Modal open onClose={onClose} width={520} title={t('alm.invoice_accept_title', { number: factura.number })}>
      <label className="alm-label" htmlFor="almf-nota">{t('alm.invoice_accept_note')} *</label>
      <textarea id="almf-nota" rows={3} className="alm-input" value={nota} onChange={e => setNota(e.target.value)} />
      {error && <p className="u-field-error" role="alert">{error}</p>}
      <div className="almf-acciones-modal">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => mutate()} loading={isPending} disabled={isPending || !nota.trim()}>{t('alm.invoice_accept')}</Button>
      </div>
    </Modal>
  )
}

export default function ConciliacionTab() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [estado, setEstado] = useState('')
  const [pagina, setPagina] = useState(1)
  const [editar, setEditar] = useState<FacturaDeProveedor | null | undefined>(undefined)
  const [enlazar, setEnlazar] = useState<FacturaDeProveedor | null>(null)
  const [aceptar, setAceptar] = useState<FacturaDeProveedor | null>(null)
  const facturas = useQuery({
    queryKey: ['alm-invoices', estado, pagina],
    queryFn: () => almApi.facturas({ status: estado || undefined, page: pagina, page_size: POR_PAGINA }),
  })
  const faltan = useQuery({ queryKey: ['alm-invoices', 'missing'], queryFn: () => almApi.facturasQueFaltan(12) })
  const reconciliar = useMutation({
    mutationFn: (id: string) => almApi.conciliar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-invoices'] }),
    onError: e => toast.error(errorAlm(t, e)),
  })
  const borrar = useMutation({
    mutationFn: (id: string) => almApi.borrarFactura(id),
    onSuccess: () => CLAVES.forEach(k => qc.invalidateQueries({ queryKey: [k] })),
    onError: e => toast.error(errorAlm(t, e)),
  })
  const subirPdf = useMutation({
    mutationFn: ({ id, f }: { id: string; f: File }) => almApi.subirPdfDeFactura(id, f),
    onSuccess: () => toast.success(t('alm.attachment_uploaded')),
    onError: e => toast.error(errorAlm(t, e)),
  })
  const filas = facturas.data?.items ?? []
  const paginas = Math.max(1, Math.ceil((facturas.data?.total ?? 0) / POR_PAGINA))
  return (
    <div className="u-stack-14">
      <div className="alm-toolbar">
        <Select suelto placeholder={false} aria-label={t('alm.status')} className="alm-input alm-toolbar__select--fixed" value={estado} onChange={e => { setEstado(e.target.value); setPagina(1) }}>
          <option value="">{t('alm.filter_all')}</option>
          {['pending', 'matched', 'discrepancy', 'accepted'].map(s => <option key={s} value={s}>{t(`alm.st_${s}`)}</option>)}
        </Select>
        <Button icon={<Plus size={14} />} onClick={() => setEditar(null)}>{t('alm.invoice_new')}</Button>
      </div>
      <p className="alm-hint">{t('alm.reconciliation_hint')}</p>

      {(faltan.data ?? []).length > 0 && (
        <Section title={t('alm.invoices_missing_title', { n: faltan.data?.length ?? 0 })} subtitle={t('alm.invoices_missing_hint')}>
          <ul className="almf-lista">
            {(faltan.data ?? []).slice(0, 12).map(p => (
              <li key={`${p.contract_id}-${p.period_from}`} className="almf-fila">
                <span className="almf-fila__nombre"><FileWarning size={14} aria-hidden="true" />{p.contract_title}</span>
                <span className="almf-fila__meta">
                  {p.vendor_name && <span>{p.vendor_name}</span>}
                  <span>{fmtDate(p.period_from)} – {fmtDate(p.period_to)}</span>
                  {p.expected_amount != null && <span className="almf-importe">{fmtCurrency(p.expected_amount, p.currency)}</span>}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {facturas.isLoading ? <Spinner /> : filas.length === 0 ? (
        <EmptyState svgIcon={<FileWarning size={32} />} title={t('alm.invoices_empty')} description={t('alm.invoices_empty_desc')} />
      ) : (
        <ul className="almf-lista">
          {filas.map(f => (
            <li key={f.id} className="almf-fila">
              <div className="almf-fila__principal">
                <span className="almf-fila__nombre">{f.number}{f.vendor_name ? ` · ${f.vendor_name}` : ''}<EstadoAlm t={t} codigo={f.status} /></span>
                <span className="almf-fila__meta">
                  <span>{fmtDate(f.issue_date)}</span>
                  {f.contract_title && <span>{f.contract_title}</span>}
                  {f.period_from && <span>{fmtDate(f.period_from)} – {fmtDate(f.period_to)}</span>}
                  <span className="almf-importe">{fmtCurrency(f.amount, f.currency)}</span>
                  {f.expected_amount != null && <span>{t('alm.invoice_expected', { amount: fmtCurrency(f.expected_amount, f.currency) })}</span>}
                  {f.difference != null && f.difference !== 0 && (
                    <span className={f.difference > 0 ? 'almf-negativo' : 'almf-positivo'}>{t('alm.invoice_difference', { amount: fmtCurrency(f.difference, f.currency) })}</span>
                  )}
                  {f.expense && <span>{t('alm.invoice_paid_by', { code: f.expense.code })}</span>}
                </span>
                {f.issues.length > 0 && (
                  <span className="almf-pills">
                    {f.issues.map(c => <span key={c} className="alm-issue-pill alm-issue-pill--warning">{t(`alm.rec_${c}`, c)}</span>)}
                  </span>
                )}
                {f.notes && <span className="almf-evento__motivo">{f.notes}</span>}
              </div>
              <div className="almf-fila__acciones">
                <Button size="sm" variant="secondary" icon={<Link2 size={14} />} onClick={() => setEnlazar(f)}>
                  {f.expense_id ? t('alm.invoice_change_expense') : t('alm.invoice_link_expense_short')}
                </Button>
                {f.status === 'discrepancy' && <Button size="sm" variant="secondary" onClick={() => setAceptar(f)}>{t('alm.invoice_accept')}</Button>}
                <Button size="sm" variant="ghost" icon={<RefreshCw size={14} />} onClick={() => reconciliar.mutate(f.id)}>{t('alm.invoice_reconcile')}</Button>
                <label className="almf-subir">
                  {t('alm.invoice_pdf')}
                  <input type="file" accept="application/pdf,image/*" onChange={e => { const file = e.target.files?.[0]; if (file) subirPdf.mutate({ id: f.id, f: file }); e.target.value = '' }} />
                </label>
                <Button size="sm" variant="ghost" onClick={() => setEditar(f)}>{t('common.edit')}</Button>
                <Button size="sm" variant="ghost" icon={<Trash2 size={14} />}
                  onClick={() => openConfirmGlobal({ message: t('alm.invoice_delete_confirm', { number: f.number }), onConfirm: () => borrar.mutate(f.id), danger: true })}>
                  {t('common.delete')}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {paginas > 1 && <Pagination page={pagina} totalPages={paginas} onChange={setPagina} total={facturas.data?.total ?? 0} pageSize={POR_PAGINA} maxVisible={5} />}
      {editar !== undefined && <NuevaFactura factura={editar} onClose={() => setEditar(undefined)} />}
      {enlazar && <EnlazarGasto factura={enlazar} onClose={() => setEnlazar(null)} />}
      {aceptar && <AceptarDiscrepancia factura={aceptar} onClose={() => setAceptar(null)} />}
    </div>
  )
}
