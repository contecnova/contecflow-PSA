/**
 * IntakeFormPage — Public-facing form, no auth required.
 * Route: /intake/:token
 */
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import axios from 'axios'
import { useAppT } from '../i18n/AppLangContext'

const BASE_URL = import.meta.env.VITE_API_URL || ''

const FS = {
  width: '100%', background: '#fff', border: '1px solid #d1d5db',
  borderRadius: 8, padding: '10px 14px', color: '#111827', fontSize: 14,
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
}
const LS = { fontSize: 13, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 6 }

export default function IntakeFormPage() {
  const { token } = useParams()
  const t = useAppT()

  const { data: form, isLoading, error } = useQuery({
    queryKey: ['public-form', token],
    queryFn: () => axios.get(`${BASE_URL}/api/v1/forms/public/${token}`).then(r => r.data),
    retry: false,
  })

  const [fields, setFields] = useState({
    subject: '', description: '', submitter_name: '', submitter_email: '', priority: '',
  })
  const [submitted, setSubmitted] = useState(false)
  const set = k => e => setFields(p => ({ ...p, [k]: e.target.value }))

  const { mutate, isPending, isError, error: submitError } = useMutation({
    mutationFn: (data) => axios.post(`${BASE_URL}/api/v1/forms/public/${token}/submit`, data).then(r => r.data),
    onSuccess: () => setSubmitted(true),
  })

  if (isLoading) return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <p style={{ color: '#6b7280', textAlign: 'center' }}>{t('intake_form.loading_message')}</p>
      </div>
    </div>
  )

  if (error || !form) return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <h2 style={{ color: '#dc2626', fontSize: 20, marginBottom: 8 }}>{t('intake_form.error_not_found_title')}</h2>
        <p style={{ color: '#6b7280' }}>{t('intake_form.error_not_found_message')}</p>
      </div>
    </div>
  )

  if (submitted) return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <div style={{ fontSize: 48, textAlign: 'center', marginBottom: 16 }}>✅</div>
        <h2 style={{ fontSize: 22, fontWeight: 700, textAlign: 'center', color: '#111827', marginBottom: 10 }}>
          {t('intake_form.success_title')}
        </h2>
        <p style={{ color: '#6b7280', textAlign: 'center', lineHeight: 1.6 }}>
          {form.success_message || t('intake_form.success_default_message')}
        </p>
      </div>
    </div>
  )

  return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: '#111827', marginBottom: 6 }}>{form.name}</h1>
          {form.description && <p style={{ color: '#6b7280', fontSize: 14, lineHeight: 1.5 }}>{form.description}</p>}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <div>
              <label style={LS}>{t('intake_form.name_label')}</label>
              <input value={fields.submitter_name} onChange={set('submitter_name')} style={FS} placeholder={t('intake_form.name_placeholder')} />
            </div>
            <div>
              <label style={LS}>{t('intake_form.email_label')}</label>
              <input type="email" value={fields.submitter_email} onChange={set('submitter_email')} style={FS} placeholder={t('intake_form.email_placeholder')} />
            </div>
          </div>

          <div>
            <label style={LS}>{t('intake_form.subject_label')}</label>
            <input value={fields.subject} onChange={set('subject')} style={FS} placeholder={t('intake_form.subject_placeholder')} required />
          </div>

          <div>
            <label style={LS}>{t('intake_form.description_label')}</label>
            <textarea value={fields.description} onChange={set('description')} style={{ ...FS, resize: 'vertical' }}
              rows={5} placeholder={t('intake_form.description_placeholder')} />
          </div>

          <div>
            <label style={LS}>{t('intake_form.priority_label')}</label>
            <select value={fields.priority || form.default_priority} onChange={set('priority')} style={FS}>
              <option value="low">{t('intake_form.priority_low')}</option>
              <option value="medium">{t('intake_form.priority_medium')}</option>
              <option value="high">{t('intake_form.priority_high')}</option>
              <option value="critical">{t('intake_form.priority_critical')}</option>
            </select>
          </div>

          {isError && (
            <div style={{ background: '#fee2e2', border: '1px solid #fca5a5', borderRadius: 8, padding: '10px 14px', color: '#dc2626', fontSize: 13 }}>
              {t('intake_form.error_send_label')} {submitError?.response?.data?.detail || t('intake_form.error_retry_label')}
            </div>
          )}

          <button
            onClick={() => mutate(fields)}
            disabled={isPending || !fields.subject}
            style={{
              background: isPending ? '#9ca3af' : '#2563eb',
              color: '#fff', border: 'none', borderRadius: 10,
              padding: '12px 24px', fontSize: 14, fontWeight: 700,
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

const pageStyle = {
  minHeight: '100vh', background: '#f9fafb',
  display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
  padding: '40px 16px',
}

const cardStyle = {
  background: '#fff', borderRadius: 16, boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
  padding: '36px 32px', width: '100%', maxWidth: 600,
}
