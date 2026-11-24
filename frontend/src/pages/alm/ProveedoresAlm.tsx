/**
 * Pestaña de proveedores y su modal.
 * Troceado de ALMPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useId, useState, type CSSProperties } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { vendorsApi } from '../../services/api'
import { Buscador, Button, Spinner, EmptyState, Modal, Select, useErroresDeCampo, Input, Textarea, IconButton } from '../../components/ui'
import Pagination from '../../components/ui/Pagination'
import { Building2, Plus, Pencil, Trash2, User, Mail, Link as LinkIcon } from 'lucide-react'
import { extractErr } from '../../utils/helpers'
import { sanitizeUrl } from '../../utils/security'
import { useAppT } from '../../i18n/AppLangContext'
import {
  ALM_PAGE_SIZE,
  aPagina,
  type CambioDeCampo,
  type PaginaAlm,
  useAjustarPagina,
  useRetardado,
  type Vendor,
  VENDOR_CATS,
} from './compartidoAlm'

// ── Vendors ────────────────────────────────────────────────────────────────────
function VendorModal({ vendor, onClose }: { vendor: Partial<Vendor> | null; onClose: () => void }) {
  const t = useAppT()
  const idPrefix = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!vendor
  const [form, setForm] = useState({
    name: vendor?.name || '', category: vendor?.category || 'software',
    website: vendor?.website || '', support_email: vendor?.support_email || '',
    support_phone: vendor?.support_phone || '', account_manager: vendor?.account_manager || '',
    account_number: vendor?.account_number || '', tax_id: '',
    country: vendor?.country || 'ES', notes: vendor?.notes || '',
  })
  const s = (k: keyof typeof form) => (e: CambioDeCampo) => setForm(f => ({ ...f, [k]: e.target.value }))
  const camposD = useErroresDeCampo()
  const msgD = (k: string) => camposD.de(k) ? <div className="u-field-error">{camposD.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => camposD.limpiar(),
    // VendorSerializer no envía tax_id: en la edición el campo sale vacío y, si no se
    // escribe, no se manda (antes se mandaba '' y borraba el CIF guardado).
    mutationFn: ({ tax_id, ...resto }: typeof form) => isEdit
      ? vendorsApi.update(vendor.id, tax_id ? { ...resto, tax_id } : resto)
      : vendorsApi.create({ ...resto, tax_id }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alm-vendors'] }); qc.invalidateQueries({ queryKey: ['alm-dashboard'] }); onClose() },
    onError: (e: unknown) => { if (!camposD.recoger(e)) toast.error(extractErr(e, t('ai.generic_error'))) },
  })
  return (
    <Modal open onClose={onClose} title={isEdit ? t('alm.vendor_modal_edit') : t('alm.vendor_modal_new')} width={640}>
      <div className="u-grid2-14">
        <div className="u-col-full"><Input label={<>{t('alm.vendor_label_name')}*</>} id={`${idPrefix}-name`} value={form.name} onChange={s('name')} placeholder={t('alm.vendor_placeholder_name')} />{msgD('name')}</div>
        <div>
          <Select label={t('alm.vendor_label_category')} placeholder={false} id={`${idPrefix}-category`} value={form.category} onChange={s('category')}>
            {Object.keys(VENDOR_CATS).map(k => <option key={k} value={k}>{t(`alm.vendor_cat_${k}`)}</option>)}
          </Select>{msgD('category')}
        </div>
        <div><Input label={t('alm.vendor_label_country')} id={`${idPrefix}-country`} value={form.country} onChange={s('country')} placeholder={t('alm.ej_espana')} />{msgD('country')}</div>
        <div><Input label={t('alm.vendor_label_web')} id={`${idPrefix}-website`} value={form.website} onChange={s('website')} placeholder={t('alm.vendor_placeholder_web')} />{msgD('website')}</div>
        <div><Input label={t('alm.vendor_label_support_email')} id={`${idPrefix}-support-email`} value={form.support_email} onChange={s('support_email')} />{msgD('support_email')}</div>
        <div><Input label={t('alm.vendor_label_support_phone')} id={`${idPrefix}-support-phone`} value={form.support_phone} onChange={s('support_phone')} />{msgD('support_phone')}</div>
        <div><Input label={t('alm.vendor_label_account_manager')} id={`${idPrefix}-account-manager`} value={form.account_manager} onChange={s('account_manager')} />{msgD('account_manager')}</div>
        <div><Input label={t('alm.vendor_label_account_number')} id={`${idPrefix}-account-number`} value={form.account_number} onChange={s('account_number')} />{msgD('account_number')}</div>
        <div><Input label={t('alm.vendor_label_tax_id')} id={`${idPrefix}-tax-id`} value={form.tax_id} onChange={s('tax_id')} />{msgD('tax_id')}</div>
        <div className="u-col-full"><Textarea label={t('alm.vendor_label_notes')} id={`${idPrefix}-notes`} value={form.notes} onChange={s('notes')} rows={3} />{msgD('notes')}</div>
      </div>
      <div className="alm-modal-actions">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => mutate(form)} disabled={isPending || !form.name} loading={isPending}>
          {isPending ? t('common.saving') : isEdit ? t('common.save') : t('alm.vendor_create')}
        </Button>
      </div>
    </Modal>
  )
}

export function VendorsTab() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [modal, setModal] = useState<Partial<Vendor> | null>(null)
  const [search, setSearch] = useState('')
  const [catFilter, setCatFilter] = useState('')
  const [page, setPage] = useState(1)
  const q = useRetardado(search.trim())

  // Lista paginada en el servidor: búsqueda (q) y categoría también se filtran allí.
  const { data: pagina, isLoading } = useQuery<PaginaAlm<Vendor>>({
    queryKey: ['alm-vendors', 'pagina', q, catFilter, page],
    queryFn: () => vendorsApi.list({ q: q || undefined, category: catFilter || undefined, page, page_size: ALM_PAGE_SIZE }).then(aPagina),
    placeholderData: keepPreviousData,
  })
  const vendors = pagina?.items ?? []
  const total = pagina?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / ALM_PAGE_SIZE))
  useAjustarPagina(page, totalPages, setPage, !!pagina)
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => vendorsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-vendors'] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  return (
    <div>
      <div className="alm-toolbar alm-toolbar--vendors">
        <Buscador aria-label={t('alm.vendors_search_placeholder')} value={search} onChange={v => { setSearch(v); setPage(1) }} placeholder={t('alm.vendors_search_placeholder')} className="alm-toolbar__search" />
        <Select suelto placeholder={false} aria-label={t('alm.vendors_filter_aria')} value={catFilter} onChange={e => { setCatFilter(e.target.value); setPage(1) }} className="alm-input alm-toolbar__select">
          <option value="">{t('alm.vendors_filter_all_categories')}</option>
          {Object.keys(VENDOR_CATS).map(k => <option key={k} value={k}>{t(`alm.vendor_cat_${k}`)}</option>)}
        </Select>
        <Button onClick={() => setModal({})} icon={<Plus size={14} />}>{t('alm.vendors_new')}</Button>
      </div>

      {isLoading ? <Spinner /> : vendors.length === 0 ? (
        <EmptyState svgIcon={<Building2 size={36} />} title={t('alm.vendors_empty_title')} description={t('alm.vendors_empty_desc')} />
      ) : (
        <div className="alm-vendor-grid">
          {vendors.map(v => {
            const catKey = v.category in VENDOR_CATS ? v.category : 'other'
            const cat = VENDOR_CATS[catKey]
            return (
              <div key={v.id} className="alm-card alm-vendor" style={{ '--cat-color': cat.color } as CSSProperties}>
                <div className="alm-vendor__head">
                  <div className="u-row-center-10">
                    <div className="alm-vendor__icon" aria-hidden="true">
                      {cat.icon}
                    </div>
                    <div>
                      <div className="alm-vendor__name">{v.name}</div>
                      <div className="alm-vendor__cat">{t(`alm.vendor_cat_${catKey}`)}</div>
                    </div>
                  </div>
                  <div className="ui-acciones">
                    <IconButton variante="caja" ariaLabel={t('alm.aria_edit_vendor', { name: v.name })} onClick={() => setModal(v)}><Pencil size={14} aria-hidden="true" /></IconButton>
                    <IconButton variante="caja" tono="peligro" ariaLabel={`${t('common.delete')} ${v.name}`} onClick={() => { openConfirmGlobal({ message: `${t('alm.vendors_delete_confirm')} "${v.name}"?`, onConfirm: () => del(v.id), danger: true }) }}><Trash2 size={14} aria-hidden="true" /></IconButton>
                  </div>
                </div>
                <div className="alm-vendor__info">
                  {v.account_manager && <span className="alm-meta-ico"><User size={13} aria-hidden="true" />{v.account_manager}</span>}
                  {v.support_email   && <span className="alm-meta-ico"><Mail size={13} aria-hidden="true" />{v.support_email}</span>}
                  {v.website         && <a href={sanitizeUrl(v.website)} target="_blank" rel="noopener noreferrer" className="alm-vendor__link alm-meta-ico"><LinkIcon size={13} aria-hidden="true" />{v.website}</a>}
                </div>
                <div className="alm-vendor__foot">
                  {v.contracts_count} {t('alm.vendors_contracts_count')}
                </div>
              </div>
            )
          })}
        </div>
      )}
      <div className="alm-pagination">
        <Pagination page={page} totalPages={totalPages} onChange={setPage} total={total} pageSize={ALM_PAGE_SIZE} maxVisible={5} />
      </div>
      {modal !== null && <VendorModal vendor={Object.keys(modal).length ? modal : null} onClose={() => setModal(null)} />}
    </div>
  )
}
