/**
 * ESignPage — Electronic signature management dashboard
 * Lists all envelopes, allows creating signature requests on documents.
 */

import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { documentsApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { PenLine } from 'lucide-react'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'

const STATUS_COLORS = {
  draft:     { color: 'var(--text-2)',   bg: 'var(--surface-2)',  key: 'esign.status_draft' },
  sent:      { color: 'var(--info)',     bg: 'var(--info-bg)',    key: 'esign.status_sent' },
  delivered: { color: 'var(--info)',     bg: 'var(--info-bg)',    key: 'esign.status_delivered' },
  completed: { color: 'var(--success)',  bg: 'var(--success-bg)', key: 'esign.status_completed' },
  declined:  { color: 'var(--danger)',   bg: 'var(--danger-bg)',  key: 'esign.status_declined' },
  voided:    { color: 'var(--text-3)',   bg: 'var(--surface-3)',  key: 'esign.status_voided' },
  error:     { color: 'var(--warning)',  bg: 'var(--warning-bg)', key: 'esign.status_error' },
}

function StatusPill({ status }) {
  const t = useAppT()
  const s = STATUS_COLORS[status] || STATUS_COLORS.draft
  return (
    <span style={{
      background: s.bg, color: s.color,
      border: `1px solid ${s.color}40`,
      borderRadius: 'var(--radius-md)', padding: '2px var(--space-3)', fontSize: '11px', fontWeight: 600,
    }}>{t(s.key)}</span>
  )
}

const fs = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 'var(--radius-md)',
  padding: 'var(--space-3) var(--space-3)',
  color: 'var(--text-1)',
  fontSize: '13px',
  outline: 'none',
  fontFamily: 'var(--font-sans)',
  boxSizing: 'border-box',
}
const ls = {
  fontSize: '11px',
  fontWeight: 700,
  color: 'var(--text-2)',
  textTransform: 'uppercase',
  letterSpacing: '0.07em',
  display: 'block',
  marginBottom: 'var(--space-1)',
}

function CreateEnvelopeModal({ onClose, onCreated }) {
  const t = useAppT()
  const [form, setForm] = useState({
    document_id: '',
    subject: '',
    message: '',
    provider: 'manual',
    expires_days: 7,
  })
  const [signers, setSigners] = useState([{ name: '', email: '', routing_order: 1 }])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))
  const setSigner = (i, k, v) => setSigners(s => s.map((x, idx) => idx === i ? { ...x, [k]: v } : x))
  const addSigner = () => setSigners(s => [...s, { name: '', email: '', routing_order: s.length + 1 }])
  const removeSigner = (i) => setSigners(s => s.filter((_, idx) => idx !== i))

  const { data: documents = [] } = useQuery({
    queryKey: ['documents-list'],
    queryFn: () => documentsApi.list().then(r => Array.isArray(r.data) ? r.data : r.data?.items || []),
  })

  const submit = async () => {
    if (!form.document_id || !form.subject || signers.some(s => !s.name || !s.email)) {
      setError(t('esign.error_required_fields'))
      return
    }
    setSaving(true)
    setError('')
    try {
      const res = await api.post('/esign', { ...form, document_id: Number(form.document_id), expires_days: Number(form.expires_days), signers })
      onCreated(res.data)
      onClose()
    } catch (e) {
      const raw = e?.response?.data?.detail
      setError(Array.isArray(raw) ? raw.map(e => e.msg).join(', ') : (raw || t('esign.error_create')))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title={t('esign.create_title')} onClose={onClose} style={{ maxWidth: 560 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={ls}>{t('esign.document')}</label>
          <select value={form.document_id} onChange={set('document_id')} style={fs}>
            <option value="">{t('esign.select_document')}</option>
            {documents.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>{t('esign.subject')}</label>
          <input value={form.subject} onChange={set('subject')} style={fs} placeholder={t('esign.subject_ph')} />
        </div>
        <div>
          <label style={ls}>{t('esign.message')}</label>
          <textarea value={form.message} onChange={set('message')} style={{ ...fs, resize: 'vertical' }} rows={2} placeholder={t('esign.message_ph')} />
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1 }}>
            <label style={ls}>{t('esign.provider')}</label>
            <select value={form.provider} onChange={set('provider')} style={fs}>
              <option value="manual">{t('esign.provider_manual')}</option>
              <option value="docusign">DocuSign</option>
              <option value="adobe_sign">Adobe Sign</option>
            </select>
          </div>
          <div style={{ width: 120 }}>
            <label style={ls}>{t('esign.valid_days')}</label>
            <input type="number" value={form.expires_days} onChange={set('expires_days')} style={fs} min={1} max={30} />
          </div>
        </div>

        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <label style={ls}>{t('esign.signers')}</label>
            <button onClick={addSigner} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>+ {t('esign.add_signer')}</button>
          </div>
          {signers.map((s, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
              <input value={s.name} onChange={e => setSigner(i, 'name', e.target.value)}
                placeholder={t('esign.signer_name_ph')} style={{ ...fs, flex: 1 }} />
              <input value={s.email} onChange={e => setSigner(i, 'email', e.target.value)}
                placeholder={t('esign.signer_email_ph')} type="email" style={{ ...fs, flex: 1 }} />
              <input value={s.routing_order} onChange={e => setSigner(i, 'routing_order', Number(e.target.value))}
                type="number" min={1} style={{ ...fs, width: 56 }} title={t('esign.signer_order_ph')} />
              {signers.length > 1 && (
                <button onClick={() => removeSigner(i)} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-lg)" }}>✕</button>
              )}
            </div>
          ))}
        </div>

        {error && <div style={{ color: 'var(--danger)', fontSize: "var(--text-sm)" }}>⚠ {error}</div>}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button variant="secondary" onClick={onClose}>{t('esign.cancel')}</Button>
          <Button onClick={submit} disabled={saving}>{saving ? t('esign.creating') : t('esign.request_signature')}</Button>
        </div>
      </div>
    </Modal>
  )
}

const cell = { padding: '10px 14px', fontSize: "var(--text-base)", color: 'var(--text-1)', borderBottom: '1px solid var(--surface-4)' }
const th   = { ...cell, fontWeight: 700, fontSize: "var(--text-xs)", color: 'var(--text-2)', textTransform: 'uppercase', background: 'var(--surface-2)' }

export default function ESignPage(): JSX.Element {
  const t = useAppT()
  const [creating, setCreating]   = useState(false)
  const [detail, setDetail]       = useState(null)
  const qc = useQueryClient()

  const { data: stats } = useQuery({
    queryKey: ['esign-stats'],
    queryFn: () => api.get('/esign/summary/stats').then(r => r.data),
  })

  const { data: envelopes = [], isLoading } = useQuery({
    queryKey: ['esign-envelopes'],
    queryFn: () => api.get('/esign').then(r => r.data?.items ?? r.data ?? []),
  })

  const { mutate: voidEnv } = useMutation({
    mutationFn: (id) => api.delete(`/esign/${id}`),
    onSuccess: () => qc.invalidateQueries(['esign-envelopes', 'esign-stats']),
  })

  const { mutate: markSigned } = useMutation({
    mutationFn: ({ envelopeId, signerId }) => api.patch(`/esign/${envelopeId}/signers/${signerId}/signed`),
    onSuccess: () => { qc.invalidateQueries(['esign-envelopes']); setDetail(null) },
  })

  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

  const docusignOk = stats?.providers?.docusign_configured
  const adobeOk    = stats?.providers?.adobe_configured

  return (
    <PageShell style={{ maxWidth: 1080, margin: '0 auto' }}>
      <PageHeader
        icon={<PenLine size={18} />}
        title={t('esign.title')}
        subtitle={t('esign.subtitle')}
        action={<Button onClick={() => setCreating(true)}>✍ Nueva solicitud</Button>}
      />

      {/* Provider status */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        <ProviderBadge label="DocuSign" ok={docusignOk} />
        <ProviderBadge label="Adobe Sign" ok={adobeOk} />
        {!docusignOk && !adobeOk && (
          <a
            href="/settings"
            onClick={e => { e.preventDefault(); window.location.href = '/settings#esign' }}
            style={{ fontSize: "var(--text-sm)", color: 'var(--accent)', alignSelf: 'center', textDecoration: 'underline' }}
          >
            Configura las credenciales en Settings → E-firma
          </a>
        )}
      </div>

      {/* KPI row */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 24 }}>
          {[
            { label: 'Total',       value: stats.total,     color: 'var(--text-2)' },
            { label: 'Completadas', value: stats.completed, color: 'var(--success)' },
            { label: 'Pendientes',  value: stats.pending,   color: 'var(--info)' },
            { label: 'Rechazadas',  value: stats.declined,  color: 'var(--danger)' },
          ].map(k => (
            <div key={k.label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '13px 16px' }}>
              <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: k.color }}>{k.value}</div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2 }}>{k.label}</div>
            </div>
          ))}
        </div>
      )}

      {isLoading ? <Spinner /> : envelopes.length === 0 ? (
        <EmptyState icon="✍" title={t('esign.empty_title')}
          description={t('esign.empty_desc')} />
      ) : (
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['Asunto', 'Proveedor', 'Firmantes', 'Estado', 'Enviado', 'Vence', ''].map(h => (
                  <th key={h} style={th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {envelopes.map(env => (
                <tr key={env.id}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}>
                  <td style={cell}>
                    <button onClick={() => setDetail(env)}
                      style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit', fontSize: "var(--text-base)", textAlign: 'left', padding: 0 }}>
                      {env.subject || 'Sin asunto'}
                    </button>
                  </td>
                  <td style={cell}>
                    <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                      {env.provider === 'docusign' ? '🖊 DocuSign' : env.provider === 'adobe_sign' ? '📝 Adobe' : '✋ Manual'}
                    </span>
                  </td>
                  <td style={cell}>
                    <span style={{ fontSize: "var(--text-sm)" }}>
                      {env.signers?.filter(s => s.signed).length || 0}/{env.signers?.length || 0} firmados
                    </span>
                  </td>
                  <td style={cell}><StatusPill status={env.status} /></td>
                  <td style={{ ...cell, fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{fmtDate(env.sent_at)}</td>
                  <td style={{ ...cell, fontSize: "var(--text-xs)", color: env.expires_at && new Date(env.expires_at) < new Date() ? 'var(--danger)' : 'var(--text-2)' }}>
                    {fmtDate(env.expires_at)}
                  </td>
                  <td style={cell}>
                    {['draft','sent','delivered'].includes(env.status) && (
                      <button
                        onClick={() => { openConfirmGlobal({ message: '¿Anular esta solicitud?', onConfirm: () => voidEnv(env.id), danger: true }) }}
                        style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>
                        Anular
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create modal */}
      {creating && (
        <CreateEnvelopeModal
          onClose={() => setCreating(false)}
          onCreated={() => qc.invalidateQueries(['esign-envelopes', 'esign-stats'])}
        />
      )}

      {/* Detail modal */}
      {detail && (
        <Modal title={detail.subject || 'Detalles de firma'} onClose={() => setDetail(null)} style={{ maxWidth: 500 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <StatusPill status={detail.status} />
              <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                {detail.provider === 'docusign' ? '🖊 DocuSign' : detail.provider === 'adobe_sign' ? '📝 Adobe Sign' : '✋ Manual'}
              </span>
            </div>
            {detail.message && <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', margin: 0 }}>{detail.message}</p>}

            <div>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', marginBottom: 8 }}>FIRMANTES</div>
              {(detail.signers || []).map(s => (
                <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--surface-4)' }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: s.signed ? 'var(--success)' : 'var(--surface-5)', flexShrink: 0,
                  }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)' }}>{s.name}</div>
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{s.email} · Orden {s.routing_order}</div>
                  </div>
                  {s.signed ? (
                    <span style={{ fontSize: "var(--text-xs)", color: 'var(--success)' }}>✓ Firmado {fmtDate(s.signed_at)}</span>
                  ) : detail.provider === 'manual' ? (
                    <button
                      onClick={() => markSigned({ envelopeId: detail.id, signerId: s.id })}
                      style={{ background: 'var(--success-bg)', border: 'none', borderRadius: 6, color: 'var(--success)', padding: '4px 10px', cursor: 'pointer', fontSize: "var(--text-sm)" }}>
                      Marcar firmado
                    </button>
                  ) : (
                    <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>Pendiente</span>
                  )}
                </div>
              ))}
            </div>

            {detail.signing_url && (
              <a href={detail.signing_url} target="_blank" rel="noreferrer"
                style={{ display: 'block', background: 'var(--accent-muted)', color: 'var(--accent)', padding: '10px 14px', borderRadius: 8, fontSize: "var(--text-base)", textAlign: 'center', textDecoration: 'none' }}>
                🔗 Abrir portal de firma
              </a>
            )}
          </div>
        </Modal>
      )}
    </PageShell>
  )
}

function ProviderBadge({ label, ok }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      background: ok ? 'var(--success-bg)' : 'var(--surface-3)',
      border: `1px solid ${ok ? 'var(--success-border)' : 'var(--surface-5)'}`,
      borderRadius: 8, padding: '4px 10px', fontSize: "var(--text-sm)",
      color: ok ? 'var(--success)' : 'var(--text-3)',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: ok ? 'var(--success)' : 'var(--surface-5)' }} />
      {label} {ok ? 'conectado' : 'no configurado'}
    </span>
  )
}
