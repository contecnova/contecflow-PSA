/**
 * IntakeFormPage — Public-facing form, no auth required.
 * Route: /intake/:token
 */
import { useState, useId } from 'react'
import type { ChangeEvent, CSSProperties } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { CheckCircle2 } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { apiPublica } from '../services/api/clienteBase'
import './IntakeFormPage.css'
import { Pulsable, Select, Textarea, Input } from '../components/ui'
import { extractErr } from '../utils/helpers'

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

const FS: CSSProperties = {
  width: '100%', background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '10px 14px', color: 'var(--text-1)', fontSize: "var(--text-md)",
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
}

export default function IntakeFormPage(): JSX.Element {
  const idCampo = useId()
  const { token } = useParams<{ token: string }>()
  const t = useAppT()

  const { data: form, isLoading, error } = useQuery<PublicFormResponse>({
    queryKey: ['public-form', token],
    queryFn: () => apiPublica.get(`/forms/public/${token}`).then(r => r.data),
    retry: false,
  })

  const [fields, setFields] = useState<IntakeFields>({
    subject: '', description: '', submitter_name: '', submitter_email: '', priority: '',
  })
  const [submitted, setSubmitted] = useState(false)
  const set = (k: keyof IntakeFields) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setFields((p) => ({ ...p, [k]: e.target.value }))

  const { mutate, isPending, isError, error: submitError } = useMutation({
    // 23-11-2026 (04b M3): sin claves vacías: el servidor valida `submitter_email` como Optional[EmailStr]
    // y un '' da 422. El error se pinta en la propia página, sin toast duplicado.
    mutationFn: (data: IntakeFields) => apiPublica.post(`/forms/public/${token}/submit`, {
      subject: data.subject,
      description: data.description || undefined,
      submitter_name: data.submitter_name || undefined,
      submitter_email: data.submitter_email || undefined,
      priority: data.priority || undefined,
    }).then(r => r.data),
    onSuccess: () => setSubmitted(true),
    meta: { errorToast: false },
  })

  if (isLoading) return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <p className="intake-text">{t('intake_form.loading_message')}</p>
      </div>
    </div>
  )

  if (error || !form) return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <h2 className="intake-title">{t('intake_form.error_not_found_title')}</h2>
        <p className="u-text3">{t('intake_form.error_not_found_message')}</p>
      </div>
    </div>
  )

  if (submitted) return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <div className="intake-box"><CheckCircle2 size={48} aria-hidden /></div>
        <h2 className="intake-title-2">
          {t('intake_form.success_title')}
        </h2>
        <p className="intake-text-2">
          {form.success_message || t('intake_form.success_default_message')}
        </p>
      </div>
    </div>
  )

  return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <div className="intake-box-2">
          <h1 className="intake-title-3">{form.name}</h1>
          {form.description && <p className="intake-text-3">{form.description}</p>}
        </div>

        <div className="u-stack-16">
          <div className="u-grid2-14">
            <Input id={`${idCampo}-1`} label={t('intake_form.name_label')} value={fields.submitter_name} onChange={set('submitter_name')} placeholder={t('intake_form.name_placeholder')} />
            <Input id={`${idCampo}-2`} label={t('intake_form.email_label')} type="email" value={fields.submitter_email} onChange={set('submitter_email')} placeholder={t('intake_form.email_placeholder')} />
          </div>

          <Input id={`${idCampo}-3`} label={t('intake_form.subject_label')} value={fields.subject} onChange={set('subject')} placeholder={t('intake_form.subject_placeholder')} required />

          <Textarea label={t('intake_form.description_label')} id={`${idCampo}-4`} value={fields.description} onChange={set('description')} rows={5} placeholder={t('intake_form.description_placeholder')} />

          <Select label={t('intake_form.priority_label')} placeholder={false} id={`${idCampo}-5`} value={fields.priority || form.default_priority} onChange={set('priority')} style={FS}>
              <option value="low">{t('intake_form.priority_low')}</option>
              <option value="medium">{t('intake_form.priority_medium')}</option>
              <option value="high">{t('intake_form.priority_high')}</option>
              <option value="critical">{t('intake_form.priority_critical')}</option>
            </Select>

          {isError && (
            <div className="intake-card">
              {t('intake_form.error_send_label')} {extractErr(submitError, t('intake_form.error_retry_label'))}
            </div>
          )}

          <Pulsable
            onClick={() => mutate(fields)}
            disabled={isPending || !fields.subject}
            className={`intake-btn ${isPending ? 'intakefo-sx1' : 'intakefo-sx2'} ${isPending || !fields.subject ? 'intakefo-sx3' : 'intakefo-sx4'}`}
          >
            {isPending ? t('intake_form.sending_button') : t('intake_form.send_button')}
          </Pulsable>
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
  background: 'var(--surface-1)', borderRadius: 16, boxShadow: 'var(--shadow-md)',
  border: '1px solid var(--surface-4)',
  padding: '36px 32px', width: '100%', maxWidth: 600,
}
