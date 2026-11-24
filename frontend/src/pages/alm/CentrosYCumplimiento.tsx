/**
 * Pestañas de centros de coste y de cumplimiento.
 * Troceado de ALMPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useId, useState } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { almExtApi } from '../../services/api'
import { Button, Spinner, EmptyState, KpiCard, Input, IconButton } from '../../components/ui'
import { Briefcase, Plus, Pencil, Trash2, CheckCircle2, XCircle, RefreshCw, ShieldAlert } from 'lucide-react'
import { fmtCurrency, extractErr } from '../../utils/helpers'
import { useAppT } from '../../i18n/AppLangContext'
import { useOrgSettings } from '../../hooks/useOrgSettings'
import { type CambioDeCampo, type CostCenter, type CostCenterForm } from './compartidoAlm'

// ── Cost Centers ───────────────────────────────────────────────────────────────
export function CostCentersTab() {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { currency: defaultCurrency } = useOrgSettings()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<CostCenter | null>(null)
  const [form, setForm] = useState<CostCenterForm>({ code: '', name: '', description: '', budget_annual: '', currency: defaultCurrency })
  const s = (k: keyof CostCenterForm) => (e: CambioDeCampo) => setForm(f => ({ ...f, [k]: e.target.value }))

  const { data: centers = [], isLoading } = useQuery<CostCenter[]>({ queryKey: ['alm-cost-centers'], queryFn: () => almExtApi.costCenters().then(r => r.data) })

  const { mutate: save, isPending } = useMutation({
    mutationFn: (d: CostCenterForm) => editing ? almExtApi.updateCostCenter(editing.id, d) : almExtApi.createCostCenter(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alm-cost-centers'] }); setShowForm(false); setEditing(null); setForm({ code: '', name: '', description: '', budget_annual: '', currency: defaultCurrency }) },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => almExtApi.deleteCostCenter(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-cost-centers'] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const openEdit = (c: CostCenter) => { setEditing(c); setForm({ code: c.code, name: c.name, description: c.description || '', budget_annual: c.budget_annual || '', currency: c.currency || defaultCurrency }); setShowForm(true) }

  return (
    <div>
      <div className="u-row-end u-mb-16">
        <Button onClick={() => { setEditing(null); setShowForm(true) }} icon={<Plus size={14} />}>{t('alm.cost_centers_new')}</Button>
      </div>
      {showForm && (
        <div className="alm-card alm-cc-form">
          <h4 className="alm-cc-form__title">{editing ? t('alm.cost_centers_edit') : t('alm.cost_centers_new')}</h4>
          <div className="alm-cc-form__grid">
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="alm-label">{t('alm.cost_centers_label_code')} *</label><Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.code} onChange={s('code')} placeholder={t('alm.cost_centers_placeholder_code')} inputClassName="alm-input" /></div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="alm-label">{t('alm.cost_centers_label_name')} *</label><Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.name} onChange={s('name')} placeholder={t('alm.cost_centers_placeholder_name')} inputClassName="alm-input" /></div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="alm-label">{t('alm.cost_centers_label_budget')}</label><Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" value={form.budget_annual} onChange={s('budget_annual')} inputClassName="alm-input" /></div>
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="alm-label">{t('alm.cost_centers_label_currency')}</label><Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.currency} onChange={s('currency')} inputClassName="alm-input" /></div>
            <div className="u-col-full"><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="alm-label">{t('alm.cost_centers_label_description')}</label><Input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.description} onChange={s('description')} inputClassName="alm-input" /></div>
          </div>
          <div className="alm-cc-form__actions">
            <Button variant="secondary" onClick={() => { setShowForm(false); setEditing(null) }}>{t('common.cancel')}</Button>
            <Button onClick={() => save(form)} disabled={isPending || !form.code || !form.name} loading={isPending}>{isPending ? t('common.saving') : editing ? t('common.save') : t('alm.cost_centers_new')}</Button>
          </div>
        </div>
      )}
      {isLoading ? <Spinner /> : centers.length === 0 ? (
        <EmptyState svgIcon={<Briefcase size={36} />} title={t('alm.no_cost_centers')} description={t('alm.cost_centers_empty_desc')} />
      ) : (
        <div className="alm-cc-grid">
          {centers.map(c => (
            <div key={c.id} className="alm-card alm-cc">
              <div className="alm-cc__head">
                <div>
                  <span className="alm-cc__code">{c.code}</span>
                  <div className="alm-cc__name">{c.name}</div>
                </div>
                <div className="ui-acciones">
                  <IconButton variante="caja" ariaLabel={t('alm.aria_edit_cost_center', { name: c.name })} onClick={() => openEdit(c)}><Pencil size={13} aria-hidden="true" /></IconButton>
                  <IconButton variante="caja" tono="peligro" ariaLabel={t('alm.aria_delete_cost_center', { name: c.name })} onClick={() => { openConfirmGlobal({ message: t('alm.cost_centers_delete_confirm', { name: c.name }), onConfirm: () => del(c.id), danger: true }) }}><Trash2 size={13} aria-hidden="true" /></IconButton>
                </div>
              </div>
              {c.budget_annual && <div className="alm-cc__budget">{fmtCurrency(c.budget_annual)}{t('alm.ano')}</div>}
              {c.description && <div className="alm-cc__desc">{c.description}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Compliance ─────────────────────────────────────────────────────────────────
export function ComplianceTab() {
  const t = useAppT()
  const { data: report, isLoading, refetch } = useQuery({
    queryKey: ['alm-compliance'],
    queryFn: () => almExtApi.compliance().then(r => r.data),
  })
  const issues = report?.issues || []

  return (
    <div>
      <div className="alm-compliance-head">
        <div>
          <p className="alm-compliance-intro">
            {t('alm.compliance_intro')}
          </p>
        </div>
        <Button onClick={() => refetch()} variant="secondary" icon={<RefreshCw size={14} />}>{t('common.refresh')}</Button>
      </div>

      {isLoading ? <Spinner /> : (
        <>
          <div className="ds-grid-stats alm-compliance-stats">
            <KpiCard icon={issues.length === 0 ? <CheckCircle2 size={16} /> : <XCircle size={16} />} label={t('alm.compliance_issues')} value={issues.length} warning={issues.length > 0} />
            <KpiCard icon={<ShieldAlert size={16} />} label={t('alm.compliance_critical')} value={report?.critical || 0} danger={(report?.critical || 0) > 0} />
          </div>

          {issues.length === 0 ? (
            <div className="ds-card">
              <EmptyState icon={<CheckCircle2 size={28} />} title={t('alm.compliance_ok')} description={t('alm.compliance_ok_desc')} />
            </div>
          ) : (
            <div className="u-stack-10">
              {issues.map((iss, idx) => (
                <div key={idx} className={`alm-card alm-issue${iss.severity === 'critical' ? ' alm-issue--critical' : ''}`}>
                  <div className="u-row-between">
                    <div>
                      <div className="alm-issue__name">{iss.name}</div>
                      <div className="u-text2-sm">{t(`alm.compliance_issue_${iss.issue}`, iss.params ?? {})}</div>
                    </div>
                    <div className="u-row-center-8">
                      <span className="alm-issue-pill">
                        {t(`alm.compliance_code_${iss.issue}`, iss.issue)}
                      </span>
                      <span className={`alm-issue-pill ${iss.severity === 'critical' ? 'alm-issue-pill--critical' : 'alm-issue-pill--warning'}`}>
                        {iss.severity === 'critical' ? t('alm.compliance_severity_critical') : t('alm.compliance_severity_warning')}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
