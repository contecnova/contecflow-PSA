/**
 * Renovaciones (fase 3): contratos y licencias que renuevan, con la fecha
 * límite del preaviso, la renovación automática y el uso real; y la decisión
 * de renovar, reducir o cancelar (se aplica sola al llegar la fecha).
 */
import { useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, RefreshCw } from 'lucide-react'
import { Button, EmptyState, Modal, Spinner, StatusBadge } from '../../components/ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { almApi } from '../../services/api/alm'
import type { Renovacion, UsoDeLicencia } from '../../services/api/alm'
import { fmtCurrency, fmtDate } from '../../utils/helpers'
import { Dato, errorAlm } from '../../components/alm/almFases'

function usoDe(r: Renovacion): UsoDeLicencia[] {
  if (!r.usage) return []
  if ('licenses' in r.usage) return r.usage.licenses
  return [r.usage as UsoDeLicencia]
}

function ResumenDeUso({ r }: { r: Renovacion }) {
  const t = useAppT()
  const usos = usoDe(r)
  if (!usos.length) return <span className="almf-vacio">{t('alm.usage_none')}</span>
  return (
    <span className="almf-fila__meta">
      {usos.map((u, i) => (
        <span key={i}>
          {'name' in u && typeof (u as { name?: string }).name === 'string' ? `${(u as { name: string }).name}: ` : ''}
          {t('alm.usage_line', { assigned: u.assigned, total: u.total ?? '∞' })}
          {u.in_use != null ? ` · ${t('alm.usage_in_use_n', { n: u.in_use })}` : ` · ${t('alm.usage_no_data_yet')}`}
          {u.unused != null && u.unused > 0 ? ` · ${t('alm.usage_unused_n', { n: u.unused })}` : ''}
          {u.concurrent_peak != null ? ` · ${t('alm.peak_n', { n: u.concurrent_peak })}` : ''}
        </span>
      ))}
    </span>
  )
}

function DecisionModal({ r, onClose }: { r: Renovacion; onClose: () => void }) {
  const t = useAppT()
  const id = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const [decision, setDecision] = useState<'renew' | 'reduce' | 'cancel'>(r.decision?.decision ?? 'renew')
  const [asientos, setAsientos] = useState(r.decision?.new_seats?.toString() ?? '')
  const [coste, setCoste] = useState(r.decision?.new_annual_cost?.toString() ?? '')
  const [motivo, setMotivo] = useState(r.decision?.reason ?? '')
  const [error, setError] = useState('')
  const { mutate, isPending } = useMutation({
    mutationFn: () => almApi.decidir({
      entity_type: r.entity_type, entity_id: r.id, decision,
      new_seats: decision === 'reduce' && asientos ? Number(asientos) : null,
      new_annual_cost: decision !== 'cancel' && coste ? Number(coste) : null, reason: motivo || undefined,
    }),
    onSuccess: () => { toast.success(t('alm.renewal_decided')); qc.invalidateQueries({ queryKey: ['alm-renewals'] }); onClose() },
    onError: e => setError(errorAlm(t, e)),
  })
  return (
    <Modal open onClose={onClose} width={640} title={t('alm.renewal_decide_title', { name: r.name })}
      subtitle={r.renewal_date ? t('alm.renews_on', { date: fmtDate(r.renewal_date) }) : undefined}>
      <div className="u-stack-14">
        <dl className="almf-datos">
          <Dato etiqueta={t('alm.notice_deadline')}>{r.notice_deadline ? `${fmtDate(r.notice_deadline)} (${t('alm.days_n', { n: r.days_to_deadline ?? 0 })})` : '—'}</Dato>
          <Dato etiqueta={t('alm.contracts_label_annual_cost')}>{r.annual_cost != null ? fmtCurrency(r.annual_cost) : '—'}</Dato>
          {r.total_seats != null && <Dato etiqueta={t('alm.licenses_label_total_seats')}>{r.total_seats}</Dato>}
          <Dato etiqueta={t('alm.usage')}><ResumenDeUso r={r} /></Dato>
        </dl>
        <div className="almf-titular__tipos" role="radiogroup" aria-label={t('alm.decision')}>
          {(['renew', 'reduce', 'cancel'] as const).map(d => (
            <button key={d} type="button" role="radio" aria-checked={decision === d}
              className={`almf-chip${decision === d ? ' almf-chip--on' : ''}`} onClick={() => setDecision(d)}>
              {t(`alm.decision_${d}`)}
            </button>
          ))}
        </div>
        <p className="alm-hint">{t(`alm.decision_${decision}_hint`)}</p>
        <div className="almf-rejilla-2">
          {decision === 'reduce' && r.entity_type === 'license' && (
            <div>
              <label className="alm-label" htmlFor={`${id}-s`}>{t('alm.new_seats')}</label>
              <input id={`${id}-s`} type="number" min={0} className="alm-input" value={asientos} onChange={e => setAsientos(e.target.value)} />
            </div>
          )}
          {decision !== 'cancel' && (
            <div>
              <label className="alm-label" htmlFor={`${id}-c`}>{t('alm.new_annual_cost')}</label>
              <input id={`${id}-c`} type="number" min={0} className="alm-input" value={coste} onChange={e => setCoste(e.target.value)} />
            </div>
          )}
          <div className="almf-col-completa">
            <label className="alm-label" htmlFor={`${id}-m`}>{t('alm.reason')}{decision === 'cancel' ? ' *' : ''}</label>
            <textarea id={`${id}-m`} rows={3} className="alm-input" value={motivo} onChange={e => setMotivo(e.target.value)} />
          </div>
        </div>
        {error && <p className="u-field-error" role="alert">{error}</p>}
      </div>
      <div className="almf-acciones-modal">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant={decision === 'cancel' ? 'danger' : 'primary'} onClick={() => mutate()} loading={isPending} disabled={isPending}>
          {t('alm.decision_save')}
        </Button>
      </div>
    </Modal>
  )
}

export default function RenovacionesTab() {
  const t = useAppT()
  const [dias, setDias] = useState(120)
  const [decidir, setDecidir] = useState<Renovacion | null>(null)
  const { data = [], isLoading } = useQuery({ queryKey: ['alm-renewals', dias], queryFn: () => almApi.renovaciones(dias) })
  return (
    <div>
      <div className="almf-filtros">
        <div className="almf-filtro">
          <label className="alm-label" htmlFor="almr-dias">{t('alm.window')}</label>
          <select id="almr-dias" className="alm-input" value={dias} onChange={e => setDias(Number(e.target.value))}>
            {[30, 60, 90, 120, 180, 365].map(d => <option key={d} value={d}>{t('alm.expiring_days', { n: d })}</option>)}
          </select>
        </div>
      </div>
      <p className="alm-hint">{t('alm.renewals_hint')}</p>
      {isLoading ? <Spinner /> : data.length === 0 ? (
        <EmptyState svgIcon={<CalendarClock size={32} />} title={t('alm.renewals_empty')} />
      ) : (
        <ul className="almf-lista">
          {data.map(r => {
            const urgente = (r.days_to_deadline ?? 99) <= 7 && !r.decision
            return (
              <li key={`${r.entity_type}-${r.id}`} className="almf-fila">
                <div className="almf-fila__principal">
                  <span className="almf-fila__nombre">
                    {r.name}
                    <StatusBadge kind="neutral" caps={false}>{t(`alm.entity_${r.entity_type}`)}</StatusBadge>
                    {r.auto_renew && <StatusBadge kind="info" caps={false}><RefreshCw size={11} aria-hidden="true" /> {t('alm.auto_renew')}</StatusBadge>}
                    {r.decision
                      ? <StatusBadge kind={r.decision.decision === 'cancel' ? 'danger' : r.decision.decision === 'reduce' ? 'warning' : 'success'} caps={false}>{t(`alm.decision_${r.decision.decision}`)}</StatusBadge>
                      : <StatusBadge kind={urgente ? 'danger' : 'warning'} caps={false}>{t('alm.decision_pending')}</StatusBadge>}
                  </span>
                  <span className="almf-fila__meta">
                    {r.vendor_name && <span>{r.vendor_name}</span>}
                    {r.renewal_date && <span>{t('alm.renews_on', { date: fmtDate(r.renewal_date) })}</span>}
                    {r.notice_deadline && <span className={urgente ? 'almf-negativo' : undefined}>
                      {t('alm.notice_until', { date: fmtDate(r.notice_deadline), n: r.days_to_deadline ?? 0 })}</span>}
                    {r.annual_cost != null && <span>{fmtCurrency(r.annual_cost)}{t('alm.ano')}</span>}
                  </span>
                  <ResumenDeUso r={r} />
                  {r.decision?.reason && <span className="almf-evento__motivo">{r.decision.reason}{r.decision.decided_by_name ? ` · ${r.decision.decided_by_name}` : ''}</span>}
                </div>
                <div className="almf-fila__acciones">
                  <Button size="sm" variant={r.decision ? 'secondary' : 'primary'} onClick={() => setDecidir(r)}>
                    {r.decision ? t('alm.decision_change') : t('alm.decision_take')}
                  </Button>
                </div>
              </li>
            )
          })}
        </ul>
      )}
      {decidir && <DecisionModal r={decidir} onClose={() => setDecidir(null)} />}
    </div>
  )
}
