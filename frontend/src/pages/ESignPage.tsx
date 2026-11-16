/**
 * ESignPage — Electronic signature management dashboard
 * Lists all envelopes, allows creating signature requests on documents.
 */

import { useAppLang } from '../i18n/AppLangContext'
import { ChangeEvent, useState, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { documentsApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertTriangle, CheckCircle2, Clock, ExternalLink, FileSignature, PenLine, Plus, X, XCircle } from 'lucide-react'
import { Button, Spinner, EmptyState, Modal, KpiCard, IconButton } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { fmtDate } from '../utils/helpers'
import StatusBadge from '../components/ui/StatusBadge'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import './ESignPage.css'

type EnvelopeStatus = 'draft' | 'sent' | 'delivered' | 'completed' | 'declined' | 'voided' | 'error'

type StatusColor = {
  kind: StatusBadgeKind
  key: string
}

type Signer = {
  id: number
  name: string
  email: string
  routing_order: number
  signed?: boolean
  signed_at?: string | null
}

type Envelope = {
  id: number
  subject?: string
  message?: string
  provider: 'manual' | 'docusign' | 'adobe_sign' | string
  status: EnvelopeStatus | string
  signers?: Signer[]
  sent_at?: string | null
  expires_at?: string | null
  signing_url?: string | null
}

type ESignStats = {
  total: number
  completed: number
  pending: number
  declined: number
  providers?: {
    docusign_configured?: boolean
    adobe_configured?: boolean
  }
}

type CreateSigner = {
  name: string
  email: string
  routing_order: number
}

type CreateEnvelopeForm = {
  document_id: string
  subject: string
  message: string
  provider: 'manual' | 'docusign' | 'adobe_sign'
  expires_days: number
}

type ApiError = {
  response?: {
    data?: {
      detail?: string | Array<{ msg?: string }>
    }
  }
}

const STATUS_COLORS: Record<EnvelopeStatus, StatusColor> = {
  draft:     { kind: 'neutral', key: 'esign.status_draft' },
  sent:      { kind: 'accent',  key: 'esign.status_sent' },
  delivered: { kind: 'accent',  key: 'esign.status_delivered' },
  completed: { kind: 'success', key: 'esign.status_completed' },
  declined:  { kind: 'danger',  key: 'esign.status_declined' },
  voided:    { kind: 'neutral', key: 'esign.status_voided' },
  error:     { kind: 'warning', key: 'esign.status_error' },
}

function isEnvelopeStatus(value: string): value is EnvelopeStatus {
  return value in STATUS_COLORS
}

function StatusPill({ status }: { status: string }) {
  const t = useAppT()
  const s = isEnvelopeStatus(status) ? STATUS_COLORS[status] : STATUS_COLORS.draft
  return (
    <StatusBadge kind={s.kind}>{t(s.key)}</StatusBadge>
  )
}


function CreateEnvelopeModal({ onClose, onCreated }: { onClose: () => void; onCreated: (envelope: Envelope) => void }) {
  const idCampo = useId()
  const t = useAppT()
  const [form, setForm] = useState<CreateEnvelopeForm>({
    document_id: '',
    subject: '',
    message: '',
    provider: 'manual',
    expires_days: 7,
  })
  const [signers, setSigners] = useState<CreateSigner[]>([{ name: '', email: '', routing_order: 1 }])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const setField = <K extends keyof CreateEnvelopeForm>(k: K) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const value = k === 'expires_days' ? Number(e.target.value) : e.target.value
    setForm(f => ({ ...f, [k]: value as CreateEnvelopeForm[K] }))
  }
  const setSigner = <K extends keyof CreateSigner>(i: number, k: K, v: CreateSigner[K]) => setSigners(s => s.map((x, idx) => idx === i ? { ...x, [k]: v } : x))
  const addSigner = () => setSigners(s => [...s, { name: '', email: '', routing_order: s.length + 1 }])
  const removeSigner = (i: number) => setSigners(s => s.filter((_, idx) => idx !== i))

  const { data: documents = [] } = useQuery({
    queryKey: ['documents-list'],
    queryFn: () => documentsApi.list({}).then(r => r.data),
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
    } catch (e: unknown) {
      const err = e as ApiError
      const raw = err?.response?.data?.detail
      setError(Array.isArray(raw) ? raw.map(e => e.msg).join(', ') : (raw || t('esign.error_create')))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open title={t('esign.create_title')} onClose={onClose} width={560}>
      <div className="u-stack-14">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="esign-page-e10">{t('esign.document')}</label>
          <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.document_id} onChange={setField('document_id')} className="esign-page-e11">
            <option value="">{t('esign.select_document')}</option>
            {documents.map(d => <option key={d.id} value={d.id}>{d.title}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="esign-page-e10">{t('esign.subject')}</label>
          <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.subject} onChange={setField('subject')} className="esign-page-e11" placeholder={t('esign.subject_ph')} />
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="esign-page-e10">{t('esign.message')}</label>
          <textarea id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.message} onChange={setField('message')} className="esign-page-e2" rows={2} placeholder={t('esign.message_ph')} />
        </div>
        <div className="u-wrap-10">
          <div className="esign-box">
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="esign-page-e10">{t('esign.provider')}</label>
            <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.provider} onChange={setField('provider')} className="esign-page-e11">
              <option value="manual">{t('esign.provider_manual')}</option>
              <option value="docusign">DocuSign</option>
              <option value="adobe_sign">Adobe Sign</option>
            </select>
          </div>
          <div className="esign-box-2">
            <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="esign-page-e10">{t('esign.valid_days')}</label>
            <input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} type="number" value={form.expires_days} onChange={setField('expires_days')} className="esign-page-e11" min={1} max={30} />
          </div>
        </div>

        <div>
          <div className="esign-row">
            <label className="esign-page-e10">{t('esign.signers')}</label>
            <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={addSigner}>{t('esign.add_signer')}</Button>
          </div>
          {signers.map((s, i: number) => (
            <div key={i} className="esign-row-2">
              <input aria-label={t('esign.signer_name_ph')} value={s.name} onChange={e => setSigner(i, 'name', e.target.value)}
                placeholder={t('esign.signer_name_ph')} className="esign-page-e3" />
              <input aria-label={t('esign.signer_email_ph')} value={s.email} onChange={e => setSigner(i, 'email', e.target.value)}
                placeholder={t('esign.signer_email_ph')} type="email" className="esign-page-e3" />
              <input aria-label={t('esign.signer_order_ph')} value={s.routing_order} onChange={e => setSigner(i, 'routing_order', Number(e.target.value))}
                type="number" min={1} className="esign-page-e4" title={t('esign.signer_order_ph')} />
              {signers.length > 1 && (
                <IconButton className="esign-quitar" ariaLabel={t('esign.cancel')} onClick={() => removeSigner(i)}><X size={14} aria-hidden /></IconButton>
              )}
            </div>
          ))}
        </div>

        {error && <div className="esign-box-3 esign-aviso"><AlertTriangle size={14} aria-hidden /> {error}</div>}

        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('esign.cancel')}</Button>
          <Button onClick={submit} loading={saving}>{saving ? t('esign.creating') : t('esign.request_signature')}</Button>
        </div>
      </div>
    </Modal>
  )
}


export default function ESignPage(): JSX.Element {
  const t = useAppT()
  const [creating, setCreating]   = useState(false)
  const [detail, setDetail]       = useState<Envelope | null>(null)
  const qc = useQueryClient()

  const { data: stats } = useQuery<ESignStats>({
    queryKey: ['esign-stats'],
    queryFn: () => api.get('/esign/summary/stats').then(r => r.data),
  })

  const { data: envelopes = [], isLoading } = useQuery<Envelope[]>({
    queryKey: ['esign-envelopes'],
    queryFn: () => api.get('/esign').then(r => r.data?.items ?? r.data ?? []),
  })

  const { mutate: voidEnv } = useMutation({
    mutationFn: (id: number) => api.delete(`/esign/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['esign-envelopes'] })
      qc.invalidateQueries({ queryKey: ['esign-stats'] })
    },
  })

  const { mutate: markSigned } = useMutation({
    mutationFn: ({ envelopeId, signerId }: { envelopeId: number; signerId: number }) => api.patch(`/esign/${envelopeId}/signers/${signerId}/signed`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['esign-envelopes'] }); setDetail(null) },
  })

  const docusignOk = stats?.providers?.docusign_configured
  const adobeOk    = stats?.providers?.adobe_configured

  return (
    <PageShell>
      <PageHeader
        icon={<PenLine size={18} />}
        title={t('nav.esign')}
        subtitle={t('esign.subtitle')}
        actions={<Button icon={<Plus size={14} />} onClick={() => setCreating(true)}>{t('esign.nueva_solicitud')}</Button>}
      />

      {/* Provider status */}
      <div className="esign-row-3">
        <ProviderBadge label="DocuSign" ok={!!docusignOk} />
        <ProviderBadge label="Adobe Sign" ok={!!adobeOk} />
        {!docusignOk && !adobeOk && (
          <a
            href="/settings"
            onClick={e => { e.preventDefault(); window.location.href = '/settings#esign' }}
            className="esign-link"
          >
            {t('esign.configura_las_credenciales_en_settings_e_firma')}
          </a>
        )}
      </div>

      {/* KPI row */}
      {stats && (
        <div className="ds-grid-stats esign-kpis">
          <KpiCard icon={<FileSignature size={16} />} label={t('pagina_esign.total')} value={stats.total} />
          <KpiCard icon={<CheckCircle2 size={16} />} label={t('pagina_esign.completadas')} value={stats.completed} />
          <KpiCard icon={<Clock size={16} />} label={t('pagina_esign.pendientes')} value={stats.pending} warning={stats.pending > 0} />
          <KpiCard icon={<XCircle size={16} />} label={t('pagina_esign.rechazadas')} value={stats.declined} danger={stats.declined > 0} />
        </div>
      )}

      {isLoading ? <Spinner /> : envelopes.length === 0 ? (
        <EmptyState icon={<PenLine size={28} />} title={t('esign.empty_title')}
          description={t('esign.empty_desc')}
          action={<Button icon={<Plus size={14} />} onClick={() => setCreating(true)}>{t('esign.nueva_solicitud')}</Button>} />
      ) : (
        <div className="esign-card-2">
          <table className="u-table">
            <thead>
              <tr>
                {[t('pagina_esign.asunto'), t('pagina_esign.proveedor'), t('pagina_esign.firmantes'), t('pagina_esign.estado'), t('pagina_esign.enviado'), t('pagina_esign.vence'), ''].map((h, i) => (
                  <th key={i} className="esign-page-e12">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {envelopes.map(env => (
                <tr key={env.id} className="esign-fila">
                  <td className="esign-page-e13">
                    <button onClick={() => setDetail(env)}
                      className="esign-btn-3">
                      {env.subject || t('pagina_esign.sin_asunto')}
                    </button>
                  </td>
                  <td className="esign-page-e13">
                    <span className="u-text2-sm">
                      {env.provider === 'docusign' ? t('pagina_esign.docusign') : env.provider === 'adobe_sign' ? t('pagina_esign.adobe') : t('pagina_esign.manual')}
                    </span>
                  </td>
                  <td className="esign-page-e13">
                    <span className="u-sm">
                      {t('pagina_esign.firmados_de', { firmados: env.signers?.filter((s: Signer) => s.signed).length || 0, total: env.signers?.length || 0 })}
                    </span>
                  </td>
                  <td className="esign-page-e13"><StatusPill status={env.status} /></td>
                  <td className="esign-page-e6">{fmtDate(env.sent_at)}</td>
                  <td className={`esign-page-e7 ${env.expires_at && new Date(env.expires_at) < new Date() ? 'esign-page-m8' : 'esign-page-m9'}`}>
                    {fmtDate(env.expires_at)}
                  </td>
                  <td className="esign-page-e13">
                    {['draft','sent','delivered'].includes(env.status) && (
                      <Button size="sm" variant="danger"
                        onClick={() => { openConfirmGlobal({ message: t('pagina_esign.anular_esta_solicitud'), onConfirm: () => voidEnv(env.id), danger: true }) }}>
                        {t('pagina_esign.anular')}
                      </Button>
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
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ['esign-envelopes'] })
            qc.invalidateQueries({ queryKey: ['esign-stats'] })
          }}
        />
      )}

      {/* Detail modal */}
      {detail && (
        <Modal open title={detail.subject || t('pagina_esign.detalles_de_firma')} onClose={() => setDetail(null)} width={500}>
          <div className="u-stack-14">
            <div className="u-row-center-10">
              <StatusPill status={detail.status} />
              <span className="u-text2-sm">
                {detail.provider === 'docusign' ? t('pagina_esign.docusign') : detail.provider === 'adobe_sign' ? t('pagina_esign.adobe_sign') : t('pagina_esign.manual')}
              </span>
            </div>
            {detail.message && <p className="esign-text">{detail.message}</p>}

            <div>
              <div className="esign-box-5">{t('pagina_esign.firmantes_2')}</div>
              {(detail.signers || []).map(s => (
                <div key={s.id} className="esign-row-4">
                  <span className={`esign-label-2 ${s.signed ? 'esignpag-sx2' : 'esignpag-sx3'}`} />
                  <div className="u-flex1">
                    <div className="esign-box-6">{s.name}</div>
                    <div className="u-text2-xs">{s.email}{' '}{t('pagina_esign.orden')}{' '}{s.routing_order}</div>
                  </div>
                  {s.signed ? (
                    <span className="esign-label-3">{t('pagina_esign.firmado')}{' '}{fmtDate(s.signed_at)}</span>
                  ) : detail.provider === 'manual' ? (
                    <Button size="sm" variant="secondary" icon={<CheckCircle2 size={14} />}
                      onClick={() => markSigned({ envelopeId: detail.id, signerId: s.id })}>
                      {t('pagina_esign.marcar_firmado')}
                    </Button>
                  ) : (
                    <span className="u-text2-xs">{t('pagina_esign.pendiente')}</span>
                  )}
                </div>
              ))}
            </div>

            {detail.signing_url && (
              <a href={detail.signing_url} target="_blank" rel="noreferrer"
                className="esign-link-2">
                <ExternalLink size={14} aria-hidden /> {t('esign.abrir_portal_de_firma')}
              </a>
            )}
          </div>
        </Modal>
      )}
    </PageShell>
  )
}

function ProviderBadge({ label, ok }: { label: string; ok: boolean }) {
  const { t } = useAppLang()
  return (
    <StatusBadge kind={ok ? 'success' : 'neutral'} dot caps={false}>
      {label} {ok ? t('pagina_esign.conectado') : t('pagina_esign.no_configurado')}
    </StatusBadge>
  )
}
