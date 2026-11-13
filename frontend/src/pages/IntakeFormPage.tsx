/**
 * IntakeFormPage — Public-facing form, no auth required.
 * Route: /intake/:token
 */
import { useState, useId } from 'react'
import type { ChangeEvent, CSSProperties } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import axios from 'axios'
import { useAppT } from '../i18n/AppLangContext'
import { apiUrl } from '../services/api/urls'

// axios directo y no el cliente de la app: formulario público, sin sesión que
// refrescar ni redirección a login si responde 401.

interface PublicFormResponse {
  name?: string
  description?: string
  success_message?: string
  default_priority?: string
}

interface IntakeFields {
  subject: string
  description: string
  submitter_name: string
  submitter_email: string
  priority: string
}

function extractSubmitError(error: unknown): string {
  if (typeof error !== 'object' || error == null) return ''
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
  return detail ? String(detail) : ''
}

const FS: CSSProperties = {
  width: '100%', background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '10px 14px', color: 'var(--text-1)', fontSize: "var(--text-md)",
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
}
const LS: CSSProperties = { fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 6 }

export default function IntakeFormPage(): JSX.Element {
  const idCampo = useId()
  const { token } = useParams<{ token: string }>()
  const t = useAppT()

  const { data: form, isLoading, error } = useQuery<PublicFormResponse>({
    queryKey: ['public-form', token],
    queryFn: () => axios.get(apiUrl(`/forms/public/${token}`)).then(r => r.data),
    retry: false,
  })

  const [fields, setFields] = useState<IntakeFields>({
    subject: '', description: '', submitter_name: '', submitter_email: '', priority: '',
  })
  const [submitted, setSubmitted] = useState(false)
  const set = (k: keyof IntakeFields) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setFields((p) => ({ ...p, [k]: e.target.value }))

  const { mutate, isPending, isError, error: submitError } = useMutation({
    mutationFn: (data: IntakeFields) => axios.post(apiUrl(`/forms/public/${token}/submit`), data).then(r => r.data),
    onSuccess: () => setSubmitted(true),
  })

  if (isLoading) return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <p style={{ color: 'var(--text-3)', textAlign: 'center' }}>{t('intake_form.loading_message')}</p>
      </div>
    </div>
  )

  if (error || !form) return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <h2 style={{ color: 'var(--danger)', fontSize: "var(--text-xl)", marginBottom: 8 }}>{t('intake_form.error_not_found_title')}</h2>
        <p className="u-text3">{t('intake_form.error_not_found_message')}</p>
      </div>
    </div>
  )

  if (submitted) return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <div style={{ fontSize: "var(--text-6xl)", textAlign: 'center', marginBottom: 16 }}>✅</div>
        <h2 style={{ fontSize: "var(--text-xl-em)", fontWeight: 700, textAlign: 'center', color: 'var(--text-1)', marginBottom: 10 }}>
          {t('intake_form.success_title')}
        </h2>
        <p style={{ color: 'var(--text-3)', textAlign: 'center', lineHeight: 1.6 }}>
          {form.success_message || t('intake_form.success_default_message')}
        </p>
      </div>
    </div>
  )

  return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: "var(--text-xl-em)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 6 }}>{form.name}</h1>
          {form.description && <p style={{ color: 'var(--text-3)', fontSize: "var(--text-md)", lineHeight: 1.5 }}>{form.description}</p>}
        </div>

        <div className="u-stack-16">
          <div className="u-grid2-14">
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={LS}>{t('intake_form.name_label')}</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={fields.submitter_name} onChange={set('submitter_name')} style={FS} placeholder={t('intake_form.name_placeholder')} />
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={LS}>{t('intake_form.email_label')}</label>
              <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="email" value={fields.submitter_email} onChange={set('submitter_email')} style={FS} placeholder={t('intake_form.email_placeholder')} />
            </div>
          </div>

          <div>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={LS}>{t('intake_form.subject_label')}</label>
            <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={fields.subject} onChange={set('subject')} style={FS} placeholder={t('intake_form.subject_placeholder')} required />
          </div>

          <div>
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={LS}>{t('intake_form.description_label')}</label>
            <textarea id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={fields.description} onChange={set('description')} style={{ ...FS, resize: 'vertical' }}
              rows={5} placeholder={t('intake_form.description_placeholder')} />
          </div>

          <div>
            <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={LS}>{t('intake_form.priority_label')}</label>
            <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={fields.priority || form.default_priority} onChange={set('priority')} style={FS}>
              <option value="low">{t('intake_form.priority_low')}</option>
              <option value="medium">{t('intake_form.priority_medium')}</option>
              <option value="high">{t('intake_form.priority_high')}</option>
              <option value="critical">{t('intake_form.priority_critical')}</option>
            </select>
          </div>

          {isError && (
            <div style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 8, padding: '10px 14px', color: 'var(--danger)', fontSize: "var(--text-base)" }}>
              {t('intake_form.error_send_label')} {extractSubmitError(submitError) || t('intake_form.error_retry_label')}
            </div>
          )}

          <button
            onClick={() => mutate(fields)}
            disabled={isPending || !fields.subject}
            style={{
              background: isPending ? 'var(--text-3)' : 'var(--accent)',
              color: 'var(--on-accent-light)', border: 'none', borderRadius: 'var(--radius-md)',
              padding: '12px 24px', fontSize: "var(--text-md)", fontWeight: 700,
              cursor: isPending || !fields.subject ? 'not-allowed' : 'pointer',
              fontFamily: 'inherit', transition: 'background 0.2s',
            }}
          >
            {isPending ? t('intake_form.sending_button') : t('intake_form.send_button')}
          </button>
        </div>
      </div>
    </div>
  )
}

const pageStyle: CSSProperties = {
  minHeight: '100vh', background: 'var(--surface-0)',
  display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
  padding: '40px 16px',
}

const cardStyle: CSSProperties = {
  background: 'var(--surface-1)', borderRadius: 16, boxShadow: '0 4px 24px rgba(0,0,0,0.25)',
  border: '1px solid var(--surface-4)',
  padding: '36px 32px', width: '100%', maxWidth: 600,
}
