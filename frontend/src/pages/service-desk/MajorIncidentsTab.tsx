import { useState, useId } from 'react'
import type { ChangeEvent, CSSProperties } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Spinner, Modal, useSort, SortableTH } from '../../components/ui'
import { COLOR } from '../../constants/theme'
import { majorIncidentsApi } from '../../services/api'
import { fmtDate } from './sdUtils'

interface MajorIncident {
  id: string | number
  number?: string
  title?: string
  severity?: string
  status?: string
  commander?: string
  declared_at?: string
  resolved_at?: string | null
}

interface DeclareMIForm {
  title: string
  severity: string
  impact_statement: string
}

function DeclareMIModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const idPrefix = useId()
  const [form, setForm] = useState<DeclareMIForm>({ title: '', severity: 'P1', impact_statement: '' })
  const { mutate, isPending } = useMutation({
    mutationFn: (data: DeclareMIForm) => majorIncidentsApi.create(data),
    onSuccess: onSaved,
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const set = (k: keyof DeclareMIForm) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))
  const IS: CSSProperties = {
    width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)",
    outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
  }
  const LS: CSSProperties = {
    fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', display: 'block',
    marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em',
  }
  return (
    <Modal open title={`🚨 ${t('service_desk.mi_declare_btn')}`} onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <label htmlFor={`${idPrefix}-title`} style={LS}>{t('service_desk.mi_title_lbl')} *</label>
          <input id={`${idPrefix}-title`} value={form.title} onChange={set('title')} style={IS} />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-severity`} style={LS}>{t('service_desk.mi_severity_lbl')}</label>
          <select id={`${idPrefix}-severity`} value={form.severity} onChange={set('severity')} style={IS}>
            <option value="P1">P1 — {t('service_desk.mi_severity')} (P1)</option>
            <option value="P2">P2 — {t('service_desk.mi_severity')} (P2)</option>
          </select>
        </div>
        <div>
          <label htmlFor={`${idPrefix}-impact`} style={LS}>{t('service_desk.mi_impact_lbl')}</label>
          <textarea id={`${idPrefix}-impact`} value={form.impact_statement} onChange={set('impact_statement')}
            rows={3} style={{ ...IS, resize: 'vertical' }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button
            onClick={() => mutate(form)}
            disabled={isPending || !form.title}
            loading={isPending}
            style={{ background: `${COLOR.danger}20`, color: COLOR.danger, border: `1px solid ${COLOR.danger}40` }}
          >
            {t('service_desk.mi_declare_btn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function MajorIncidentsTab() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showDeclare, setShowDeclare] = useState(false)

  const { data: mis = [], isLoading } = useQuery<MajorIncident[]>({
    queryKey: ['sd-major-incidents'],
    queryFn: () => majorIncidentsApi.list().then(r => r.data),
    refetchInterval: 30000,
  })

  const activeMis = mis.filter(m => m.status === 'active')
  const { sort: miSort, setSort: setMiSort, sortedData: sortedMis } = useSort(mis, 'declared_at', 'desc')
  const sortedMajorIncidents = sortedMis as unknown as MajorIncident[]

  return (
    <div>
      {activeMis.length > 0 && (
        <div style={{
          background: `${COLOR.danger}15`, border: `1px solid ${COLOR.danger}40`,
          borderRadius: 12, padding: '16px 20px', marginBottom: 20,
        }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: COLOR.danger, marginBottom: 10 }}>
            🚨 {activeMis.length} {t('service_desk.mi_declared_at').toLowerCase()}{activeMis.length > 1 ? 's' : ''}
          </div>
          {activeMis.map(m => (
            <div key={m.id} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 0', borderTop: `1px solid ${COLOR.danger}20`,
            }}>
              <div>
                <span style={{ fontWeight: 600, fontSize: "var(--text-sm)", color: COLOR.danger, marginRight: 10 }}>{m.number}</span>
                <span style={{ fontSize: "var(--text-base)", color: 'var(--text-1)' }}>{m.title}</span>
              </div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{t('service_desk.mi_declared_at')} {fmtDate(m.declared_at)}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>{mis.length} incidentes mayores registrados</div>
        <Button
          onClick={() => setShowDeclare(true)}
          style={{ background: `${COLOR.danger}20`, color: COLOR.danger, border: `1px solid ${COLOR.danger}40` }}
        >
          🚨 {t('service_desk.mi_declare_btn')}
        </Button>
      </div>

      {isLoading ? <Spinner /> : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--surface-4)' }}>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="number" sort={miSort} onSort={setMiSort}>{t('service_desk.col_number')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="title" sort={miSort} onSort={setMiSort}>{t('service_desk.ticket_title')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="severity" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_severity')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="status" sort={miSort} onSort={setMiSort}>{t('service_desk.ticket_status')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="commander" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_commander')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="declared_at" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_declared_at')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="resolved_at" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_resolved_at')}</SortableTH></th>
            </tr>
          </thead>
          <tbody>
            {sortedMajorIncidents.map((m) => (
              <tr key={m.id} style={{ borderBottom: '1px solid var(--surface-4)' }}>
                <td style={{ padding: '10px 8px', fontSize: "var(--text-sm)", color: COLOR.danger, fontWeight: 700 }}>{m.number}</td>
                <td style={{ padding: '10px 8px', fontSize: "var(--text-base)", color: 'var(--text-1)' }}>{m.title}</td>
                <td style={{ padding: '10px 8px' }}>
                  <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: m.severity === 'P1' ? COLOR.danger : 'var(--orange)' }}>{m.severity}</span>
                </td>
                <td style={{ padding: '10px 8px' }}>
                  <span style={{
                    fontSize: "var(--text-xs)", fontWeight: 600,
                    color: m.status === 'active' ? COLOR.danger : COLOR.success,
                    background: m.status === 'active' ? `${COLOR.danger}15` : `${COLOR.success}15`,
                    padding: '2px 8px', borderRadius: 4,
                  }}>{m.status}</span>
                </td>
                <td style={{ padding: '10px 8px', fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{m.commander || '—'}</td>
                <td style={{ padding: '10px 8px', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{m.declared_at ? fmtDate(m.declared_at) : '—'}</td>
                <td style={{ padding: '10px 8px', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{m.resolved_at ? fmtDate(m.resolved_at) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showDeclare && (
        <DeclareMIModal
          onClose={() => setShowDeclare(false)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['sd-major-incidents'] })
            setShowDeclare(false)
            toast.success(t('service_desk.mi_declared_success'))
          }}
        />
      )}
    </div>
  )
}
