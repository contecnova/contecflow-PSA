/**
 * ESignPage — Electronic signature management dashboard
 * Lists all envelopes, allows creating signature requests on documents.
 */

import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'

const STATUS_COLORS = {
  draft:     { color: 'var(--text-2)',   bg: 'var(--surface-2)',  label: 'Borrador' },
  sent:      { color: 'var(--info)',     bg: 'var(--info-bg)',    label: 'Enviado' },
  delivered: { color: 'var(--info)',     bg: 'var(--info-bg)',    label: 'Entregado' },
  completed: { color: 'var(--success)',  bg: 'var(--success-bg)', label: 'Completado' },
  declined:  { color: 'var(--danger)',   bg: 'var(--danger-bg)',  label: 'Rechazado' },
  voided:    { color: 'var(--text-3)',   bg: 'var(--surface-3)',  label: 'Anulado' },
  error:     { color: 'var(--warning)',  bg: 'var(--warning-bg)', label: 'Error' },
}

function StatusPill({ status }) {
  const s = STATUS_COLORS[status] || STATUS_COLORS.draft
  return (
    <span style={{
      background: s.bg, color: s.color,
      border: `1px solid ${s.color}40`,
      borderRadius: 12, padding: '2px 10px', fontSize: 11, fontWeight: 600,
    }}>{s.label}</span>
  )
}

const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

function CreateEnvelopeModal({ onClose, onCreated }) {
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
    queryFn: () => api.get('/documents').then(r => Array.isArray(r.data) ? r.data : r.data?.items || []),
  })

  const submit = async () => {
    if (!form.document_id || !form.subject || signers.some(s => !s.name || !s.email)) {
      setError('Completa todos los campos obligatorios')
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
      setError(Array.isArray(raw) ? raw.map(e => e.msg).join(', ') : (raw || 'Error al crear la solicitud'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Nueva solicitud de firma" onClose={onClose} style={{ maxWidth: 560 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={ls}>Documento *</label>
          <select value={form.document_id} onChange={set('document_id')} style={fs}>
            <option value="">Selecciona un documento...</option>
            {documents.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Asunto *</label>
          <input value={form.subject} onChange={set('subject')} style={fs} placeholder="Firma del contrato de servicio" />
        </div>
        <div>
          <label style={ls}>Mensaje (opcional)</label>
          <textarea value={form.message} onChange={set('message')} style={{ ...fs, resize: 'vertical' }} rows={2} placeholder="Por favor, firma este documento antes de..." />
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1 }}>
            <label style={ls}>Proveedor</label>
            <select value={form.provider} onChange={set('provider')} style={fs}>
              <option value="manual">Manual (sin integración)</option>
              <option value="docusign">DocuSign</option>
              <option value="adobe_sign">Adobe Sign</option>
            </select>
          </div>
          <div style={{ width: 120 }}>
            <label style={ls}>Válido (días)</label>
            <input type="number" value={form.expires_days} onChange={set('expires_days')} style={fs} min={1} max={30} />
          </div>
        </div>

        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <label style={ls}>Firmantes *</label>
            <button onClick={addSigner} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 12 }}>+ Añadir</button>
          </div>
          {signers.map((s, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
              <input value={s.name} onChange={e => setSigner(i, 'name', e.target.value)}
                placeholder="Nombre" style={{ ...fs, flex: 1 }} />
              <input value={s.email} onChange={e => setSigner(i, 'email', e.target.value)}
                placeholder="Email" type="email" style={{ ...fs, flex: 1 }} />
              <input value={s.routing_order} onChange={e => setSigner(i, 'routing_order', Number(e.target.value))}
                type="number" min={1} style={{ ...fs, width: 56 }} title="Orden" />
              {signers.length > 1 && (
                <button onClick={() => removeSigner(i)} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 16 }}>✕</button>
              )}
            </div>
          ))}
        </div>

        {error && <div style={{ color: 'var(--danger)', fontSize: 12 }}>⚠ {error}</div>}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={submit} disabled={saving}>{saving ? 'Creando...' : '✍ Solicitar firma'}</Button>
        </div>
      </div>
    </Modal>
  )
}

const cell = { padding: '10px 14px', fontSize: 13, color: 'var(--text-1)', borderBottom: '1px solid var(--surface-4)' }
const th   = { ...cell, fontWeight: 700, fontSize: 11, color: 'var(--text-2)', textTransform: 'uppercase', background: 'var(--surface-2)' }

export default function ESignPage() {
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
    queryFn: () => api.get('/esign').then(r => r.data),
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
    <div style={{ padding: 32, maxWidth: 1080, margin: '0 auto' }}>
      <PageHeader
        title={t('esign.title')}
        subtitle={t('esign.subtitle')}
        action={<Button onClick={() => setCreating(true)}>✍ Nueva solicitud</Button>}
      />

      {/* Provider status */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        <ProviderBadge label="DocuSign" ok={docusignOk} />
        <ProviderBadge label="Adobe Sign" ok={adobeOk} />
        {!docusignOk && !adobeOk && (
          <span style={{ fontSize: 12, color: 'var(--text-2)', alignSelf: 'center' }}>
            Configura las credenciales en Settings → E-firma para habilitar las integraciones.
          </span>
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
              <div style={{ fontSize: 22, fontWeight: 800, color: k.color }}>{k.value}</div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>{k.label}</div>
            </div>
          ))}
        </div>
      )}

      {isLoading ? <Spinner /> : envelopes.length === 0 ? (
        <EmptyState icon="✍" title="Sin solicitudes de firma"
          description="Crea tu primera solicitud para pedir la firma electrónica de un documento." />
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
                      style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, textAlign: 'left', padding: 0 }}>
                      {env.subject || 'Sin asunto'}
                    </button>
                  </td>
                  <td style={cell}>
                    <span style={{ fontSize: 12, color: 'var(--text-2)' }}>
                      {env.provider === 'docusign' ? '🖊 DocuSign' : env.provider === 'adobe_sign' ? '📝 Adobe' : '✋ Manual'}
                    </span>
                  </td>
                  <td style={cell}>
                    <span style={{ fontSize: 12 }}>
                      {env.signers?.filter(s => s.signed).length || 0}/{env.signers?.length || 0} firmados
                    </span>
                  </td>
                  <td style={cell}><StatusPill status={env.status} /></td>
                  <td style={{ ...cell, fontSize: 11, color: 'var(--text-2)' }}>{fmtDate(env.sent_at)}</td>
                  <td style={{ ...cell, fontSize: 11, color: env.expires_at && new Date(env.expires_at) < new Date() ? 'var(--danger)' : 'var(--text-2)' }}>
                    {fmtDate(env.expires_at)}
                  </td>
                  <td style={cell}>
                    {['draft','sent','delivered'].includes(env.status) && (
                      <button
                        onClick={() => { openConfirmGlobal({ message: '¿Anular esta solicitud?', onConfirm: () => voidEnv(env.id), danger: true }) }}
                        style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12 }}>
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
              <span style={{ fontSize: 12, color: 'var(--text-2)' }}>
                {detail.provider === 'docusign' ? '🖊 DocuSign' : detail.provider === 'adobe_sign' ? '📝 Adobe Sign' : '✋ Manual'}
              </span>
            </div>
            {detail.message && <p style={{ fontSize: 13, color: 'var(--text-2)', margin: 0 }}>{detail.message}</p>}

            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', marginBottom: 8 }}>FIRMANTES</div>
              {(detail.signers || []).map(s => (
                <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--surface-4)' }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: s.signed ? 'var(--success)' : 'var(--surface-5)', flexShrink: 0,
                  }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, color: 'var(--text-1)' }}>{s.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{s.email} · Orden {s.routing_order}</div>
                  </div>
                  {s.signed ? (
                    <span style={{ fontSize: 11, color: 'var(--success)' }}>✓ Firmado {fmtDate(s.signed_at)}</span>
                  ) : detail.provider === 'manual' ? (
                    <button
                      onClick={() => markSigned({ envelopeId: detail.id, signerId: s.id })}
                      style={{ background: 'var(--success-bg)', border: 'none', borderRadius: 6, color: 'var(--success)', padding: '4px 10px', cursor: 'pointer', fontSize: 12 }}>
                      Marcar firmado
                    </button>
                  ) : (
                    <span style={{ fontSize: 11, color: 'var(--text-2)' }}>Pendiente</span>
                  )}
                </div>
              ))}
            </div>

            {detail.signing_url && (
              <a href={detail.signing_url} target="_blank" rel="noreferrer"
                style={{ display: 'block', background: 'var(--accent-muted)', color: 'var(--accent)', padding: '10px 14px', borderRadius: 8, fontSize: 13, textAlign: 'center', textDecoration: 'none' }}>
                🔗 Abrir portal de firma
              </a>
            )}
          </div>
        </Modal>
      )}
    </div>
  )
}

function ProviderBadge({ label, ok }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      background: ok ? 'var(--success-bg)' : 'var(--surface-3)',
      border: `1px solid ${ok ? 'var(--success-border)' : 'var(--surface-5)'}`,
      borderRadius: 8, padding: '4px 10px', fontSize: 12,
      color: ok ? 'var(--success)' : 'var(--text-3)',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: ok ? 'var(--success)' : 'var(--surface-5)' }} />
      {label} {ok ? 'conectado' : 'no configurado'}
    </span>
  )
}
