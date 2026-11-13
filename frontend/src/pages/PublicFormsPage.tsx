/**
 * PublicFormsPage — Manage public ticket intake forms
 */
import { useState, useId } from 'react'
import type { CSSProperties, ChangeEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { formsApi } from '../services/api'
import { Button, Modal, EmptyState, Spinner, Table } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { FileText } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { extractErr, localeActivo } from '../utils/helpers'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useAppT } from '../i18n/AppLangContext'

interface PublicForm {
  id: string | number
  name: string
  description?: string
  form_type?: 'ticket' | 'task' | string
  is_active?: boolean
  default_priority?: string
  default_category?: string
  success_message?: string
  token?: string
  submission_count?: number
}

interface PublicFormPayload {
  name: string
  description: string
  form_type: string
  is_active: boolean
  default_priority: string
  default_category: string
  success_message: string
}

interface FormSubmission {
  id: string | number
  submitted_at?: string
  submitter_name?: string
  submitter_email?: string
  subject?: string
  priority?: string
  created_entity_id?: string | number
}

const FS: CSSProperties = {
  width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: "var(--text-base)",
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
}
const LS: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

function FormModal({ form, onClose }: { form?: PublicForm | null; onClose: () => void }) {
  const idCampo = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const t = useAppT()
  const isEdit = !!form

  const [f, setF] = useState<PublicFormPayload>({
    name: form?.name || '',
    description: form?.description || '',
    form_type: form?.form_type || 'ticket',
    is_active: form?.is_active ?? true,
    default_priority: form?.default_priority || 'medium',
    default_category: form?.default_category || '',
    success_message: form?.success_message || '',
  })

  const set = (k: keyof PublicFormPayload) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF(p => ({ ...p, [k]: e.target.value }))
  const setCheck = (k: keyof PublicFormPayload) => (e: ChangeEvent<HTMLInputElement>) =>
    setF(p => ({ ...p, [k]: e.target.checked }))

  const { mutate, isPending } = useMutation({
    mutationFn: (data: PublicFormPayload) => isEdit
      ? formsApi.update(form.id, data).then(r => r.data)
      : formsApi.create(data).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['public-forms'] })
      toast.success(isEdit ? t('public_forms.form_updated') : t('public_forms.form_created'))
      onClose()
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('public_forms.save_error'))),
  })

  return (
    <Modal open title={isEdit ? `${t('public_forms.edit_form')} — ${form.name}` : t('public_forms.new_form_title')} onClose={onClose} width={520}>
      <div className="u-stack-14">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={LS}>{t('public_forms.name_label')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={f.name} onChange={set('name')} style={FS} placeholder={t('public_forms.name_placeholder')} />
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={LS}>{t('public_forms.description_label')}</label>
          <textarea id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={f.description} onChange={set('description')} style={{ ...FS, resize: 'vertical' }} rows={2} />
        </div>
        <div className="u-grid2-12">
          <div>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={LS}>{t('public_forms.type_label')}</label>
            <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={f.form_type} onChange={set('form_type')} style={FS}>
              <option value="ticket">{t('public_forms.type_ticket')}</option>
              <option value="task">{t('public_forms.type_task')}</option>
            </select>
          </div>
          <div>
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={LS}>{t('public_forms.default_priority_label')}</label>
            <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={f.default_priority} onChange={set('default_priority')} style={FS}>
              <option value="low">{t('public_forms.priority_low')}</option>
              <option value="medium">{t('public_forms.priority_medium')}</option>
              <option value="high">{t('public_forms.priority_high')}</option>
              <option value="critical">{t('public_forms.priority_critical')}</option>
            </select>
          </div>
        </div>
        <div>
          <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={LS}>{t('public_forms.default_category_label')}</label>
          <input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={f.default_category} onChange={set('default_category')} style={FS} placeholder={t('public_forms.default_category_placeholder')} />
        </div>
        <div>
          <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={LS}>{t('public_forms.success_message_label')}</label>
          <textarea id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={f.success_message} onChange={set('success_message')} style={{ ...FS, resize: 'vertical' }} rows={2}
            placeholder={t('public_forms.success_message_placeholder')} />
        </div>
        <label className="u-row-center-8-pointer">
          <input type="checkbox" aria-label={t('public_forms.active_form_label')} checked={f.is_active} onChange={setCheck('is_active')} />
          <span>{t('public_forms.active_form_label')}</span>
        </label>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 4 }}>
          <Button variant="secondary" onClick={onClose}>{t('public_forms.cancel')}</Button>
          <Button onClick={() => mutate(f)} disabled={isPending || !f.name} loading={isPending}>
            {isEdit ? t('public_forms.save_changes') : t('public_forms.create_form')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function SubmissionsModal({ form, onClose }: { form: PublicForm; onClose: () => void }) {
  const t = useAppT()
  const { data: subs = [], isLoading } = useQuery<FormSubmission[]>({
    queryKey: ['form-submissions', form.id],
    queryFn: () => formsApi.submissions(form.id).then(r => r.data),
  })

  return (
    <Modal open title={`${t('public_forms.submissions_title')} — ${form.name}`} onClose={onClose} width={700}>
      {isLoading ? <Spinner /> : subs.length === 0 ? (
        <EmptyState title={t('public_forms.no_submissions')} description={t('public_forms.no_submissions_subtitle')} />
      ) : (
        <div style={{ maxHeight: 420, overflowY: 'auto' }}>
          <Table
            data={subs}
            columns={[
              { key: 'submitted_at', label: t('public_forms.col_date'), render: (_v, s) => (
                <span className="u-text2-sm">
                  {s.submitted_at ? new Date(s.submitted_at).toLocaleDateString(localeActivo()) : '—'}
                </span>
              ) },
              { key: 'submitter_name', label: t('public_forms.col_sender'), render: (_v, s) => s.submitter_name || s.submitter_email || '—' },
              { key: 'subject', label: t('public_forms.col_subject'), render: (_v, s) => <span style={{ display: 'block', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.subject}</span> },
              { key: 'priority', label: t('public_forms.col_priority'), render: (_v, s) => <span style={{ textTransform: 'capitalize', color: 'var(--text-2)' }}>{s.priority}</span> },
              { key: 'created_entity_id', label: t('public_forms.col_ticket'), render: (_v, s) => <span style={{ color: 'var(--accent)', fontSize: "var(--text-sm)" }}>{s.created_entity_id ? `#${String(s.created_entity_id).slice(0, 8)}` : '—'}</span> },
            ]}
          />
        </div>
      )}
    </Modal>
  )
}

export default function PublicFormsPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<PublicForm | null>(null)
  const [viewSubs, setViewSubs] = useState<PublicForm | null>(null)

  const { data: forms = [], isLoading } = useQuery<PublicForm[]>({
    queryKey: ['public-forms'],
    queryFn: () => formsApi.list().then(r => r.data),
  })

  const { mutate: deleteForm } = useMutation({
    mutationFn: (id: string | number) => formsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['public-forms'] }); toast.success(t('public_forms.form_deleted')) },
    onError: (e: unknown) => toast.error(extractErr(e, t('public_forms.delete_error'))),
  })

  const getPublicUrl = (token?: string) => `${window.location.origin}/intake/${token ?? ''}`

  // El widget para la web del cliente: lleva el token del FORMULARIO, que sólo
  // sirve para enviarlo (revisión 2026-11; antes pedía el token del portal).
  const getWidgetCode = (token?: string) => `<script src="${window.location.origin}/widget/ticket.js" data-form="${token ?? ''}"></script>`

  const copyLink = (token?: string, texto?: string, aviso?: string) => {
    const url = texto ?? getPublicUrl(token)
    const ok = aviso ?? t('public_forms.link_copied')
    if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(() => toast.success(ok))
    } else {
      // Fallback for non-HTTPS contexts
      const ta = document.createElement('textarea')
      ta.value = url
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      toast.success(ok)
    }
  }

  return (
    <PageShell style={{ maxWidth: 1000, margin: '0 auto' }}>
      <PageHeader
        icon={<FileText size={18} />}
        title={t('public_forms.title')}
        subtitle={t('public_forms.subtitle')}
        actions={
          <Button onClick={() => setShowCreate(true)}>+ {t('public_forms.new_form')}</Button>
        }
      />

      {isLoading ? <Spinner /> : forms.length === 0 ? (
        <EmptyState
          title={t('public_forms.empty_title')}
          description={t('public_forms.empty_subtitle')}
          action={<Button onClick={() => setShowCreate(true)}>{t('public_forms.create_form')}</Button>}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 8 }}>
          {forms.map(form => (
            <div key={form.id} style={{
              background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
              borderRadius: 12, padding: '16px 20px',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap',
            }}>
              <div style={{ flex: '1 1 280px', minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                  <span style={{ fontWeight: 700, fontSize: "var(--text-md-em)" }}>{form.name}</span>
                  <span style={{
                    fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 8px', borderRadius: 20,
                    background: form.is_active ? '#2d6a4f' : 'var(--surface-4)',
                    color: form.is_active ? '#b7e4c7' : 'var(--text-3)',
                  }}>{form.is_active ? t('public_forms.status_active') : t('public_forms.status_inactive')}</span>
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginLeft: 4, textTransform: 'capitalize' }}>
                    {form.form_type === 'ticket' ? `🎫 ${t('public_forms.type_ticket')}` : `✅ ${t('public_forms.type_task')}`}
                  </span>
                </div>
                {form.description && (
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 6 }}>{form.description}</div>
                )}
                <div style={{
                  fontSize: "var(--text-xs)", color: 'var(--text-3)', fontFamily: 'var(--font-mono)',
                  background: 'var(--surface-3)', padding: '4px 10px', borderRadius: 'var(--radius-sm)',
                  display: 'inline-block', maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {getPublicUrl(form.token)}
                </div>
                <div className="u-hint">
                  {t('public_forms.submissions_received').replace('{n}', String(form.submission_count || 0))}
                </div>
              </div>
              <div className="u-wrap-8">
                <Button variant="secondary" onClick={() => copyLink(form.token)} style={{ fontSize: "var(--text-sm)" }}>{t('public_forms.copy_link')}</Button>
                <Button variant="secondary" title={t('public_forms.copy_widget_help')}
                  onClick={() => copyLink(form.token, getWidgetCode(form.token), t('public_forms.widget_copied'))}
                  style={{ fontSize: "var(--text-sm)" }}>{t('public_forms.copy_widget')}</Button>
                <Button variant="secondary" onClick={() => setViewSubs(form)} style={{ fontSize: "var(--text-sm)" }}>{t('public_forms.submissions')}</Button>
                <Button variant="secondary" onClick={() => setEditing(form)} style={{ fontSize: "var(--text-sm)" }}>{t('public_forms.edit_form')}</Button>
                <Button variant="danger" style={{ fontSize: "var(--text-sm)" }} onClick={() =>
                  openConfirmGlobal({
                    title: t('public_forms.delete_form'),
                    message: t('public_forms.delete_confirm').replace('{name}', form.name),
                    onConfirm: () => deleteForm(form.id),
                  })
                }>{t('common.delete')}</Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && <FormModal onClose={() => setShowCreate(false)} />}
      {editing && <FormModal form={editing} onClose={() => setEditing(null)} />}
      {viewSubs && <SubmissionsModal form={viewSubs} onClose={() => setViewSubs(null)} />}
    </PageShell>
  )
}
