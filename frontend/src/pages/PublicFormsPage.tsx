/**
 * PublicFormsPage — Manage public ticket intake forms
 *
 * 16-11-2026: pasada de diseño. Fuera el ancho máximo centrado propio; título
 * del menú; «Nuevo formulario» con icono (antes «+ » en el texto); vacíos con
 * icono lucide (antes el icono de alerta «!» o ninguno); tipo con icono lucide
 * (antes emojis); estado con StatusBadge; campos del kit (antes grises
 * propios); fecha con el formateador de la app y prioridad traducida (antes el
 * código crudo).
 */
import { useState, useId } from 'react'
import type { ChangeEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { formsApi, projectsApi } from '../services/api'
import type { FormularioPublico } from '../services/api/tipos-documentos'
import { Button, Card, Input, Modal, EmptyState, Spinner, Table } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import Pagination from '../components/ui/Pagination'
import { SMALL_PAGE_SIZE } from '../constants/pagination'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { FileText, Plus, Link2, Code2, Inbox, Pencil, Trash2, Ticket, CheckSquare, Check } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { extractErr, fmtDate } from '../utils/helpers'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useAppT } from '../i18n/AppLangContext'
import './PublicFormsPage.css'

type PublicForm = FormularioPublico

/** `FormCreateIn` / `FormUpdateIn` (endpoints/public_forms.py). */
interface PublicFormPayload {
  name: string
  description: string
  form_type: FormularioPublico['form_type']
  target_project_id: string | null
  is_active: boolean
  default_priority: string
  default_category: string
  success_message: string
}


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
    target_project_id: form?.target_project_id ?? null,
    is_active: form?.is_active ?? true,
    default_priority: form?.default_priority || 'medium',
    default_category: form?.default_category || '',
    success_message: form?.success_message || '',
  })

  const set = (k: keyof PublicFormPayload) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF(p => ({ ...p, [k]: e.target.value }))
  const setCheck = (k: keyof PublicFormPayload) => (e: ChangeEvent<HTMLInputElement>) =>
    setF(p => ({ ...p, [k]: e.target.checked }))

  // Un formulario de tareas necesita proyecto destino (validar_destino): sin este
  // selector el alta de un formulario de tareas daba siempre 400.
  const { data: proyectos = [] } = useQuery({
    queryKey: ['projects-minimal'],
    queryFn: () => projectsApi.list().then(r => r.data),
    enabled: f.form_type === 'task',
  })

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
        <Input label={t('public_forms.name_label')} value={f.name} onChange={set('name')} placeholder={t('public_forms.name_placeholder')} />
        <div className="ui-field">
          <label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-2`}>{t('public_forms.description_label')}</label>
          <textarea className="ds-input pubf-textarea" id={`${idCampo}-2`} value={f.description} onChange={set('description')} rows={2} />
        </div>
        <div className="u-grid2-12">
          <div className="ui-field">
            <label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-3`}>{t('public_forms.type_label')}</label>
            <select className="ds-input" id={`${idCampo}-3`} value={f.form_type} onChange={set('form_type')} disabled={isEdit}>
              <option value="ticket">{t('public_forms.type_ticket')}</option>
              <option value="task">{t('public_forms.type_task')}</option>
            </select>
          </div>
          <div className="ui-field">
            <label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-4`}>{t('public_forms.default_priority_label')}</label>
            <select className="ds-input" id={`${idCampo}-4`} value={f.default_priority} onChange={set('default_priority')}>
              <option value="low">{t('public_forms.priority_low')}</option>
              <option value="medium">{t('public_forms.priority_medium')}</option>
              <option value="high">{t('public_forms.priority_high')}</option>
              <option value="critical">{t('public_forms.priority_critical')}</option>
            </select>
          </div>
        </div>
        {f.form_type === 'task' && (
          <div className="ui-field">
            <label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-7`}>{t('public_forms.target_project_label')}</label>
            <select className="ds-input" id={`${idCampo}-7`} value={f.target_project_id ?? ''}
              onChange={e => setF(p => ({ ...p, target_project_id: e.target.value || null }))}>
              <option value="">—</option>
              {proyectos.map(pr => <option key={pr.id} value={pr.id}>{pr.code} · {pr.name}</option>)}
            </select>
          </div>
        )}
        <Input label={t('public_forms.default_category_label')} value={f.default_category} onChange={set('default_category')} placeholder={t('public_forms.default_category_placeholder')} />
        <div className="ui-field">
          <label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-6`}>{t('public_forms.success_message_label')}</label>
          <textarea className="ds-input pubf-textarea" id={`${idCampo}-6`} value={f.success_message} onChange={set('success_message')} rows={2}
            placeholder={t('public_forms.success_message_placeholder')} />
        </div>
        <label className="u-row-center-8-pointer">
          <input type="checkbox" className="pubf-check" checked={f.is_active} onChange={setCheck('is_active')} />
          <span>{t('public_forms.active_form_label')}</span>
        </label>
        <div className="pubf-row">
          <Button variant="secondary" onClick={onClose}>{t('public_forms.cancel')}</Button>
          <Button icon={isEdit ? <Check size={14} /> : <Plus size={14} />} onClick={() => mutate(f)} disabled={!f.name || (f.form_type === 'task' && !f.target_project_id)} loading={isPending}>
            {isEdit ? t('public_forms.save_changes') : t('public_forms.create_form')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function SubmissionsModal({ form, onClose }: { form: PublicForm; onClose: () => void }) {
  const t = useAppT()
  // Paginado en el servidor (page/page_size; total en meta.total o X-Total-Count).
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({
    queryKey: ['form-submissions', form.id, page],
    queryFn: () => formsApi.submissions(form.id, { page, page_size: SMALL_PAGE_SIZE }).then(r => ({
      items: r.data,
      total: r.meta?.total ?? Number(r.headers?.['x-total-count'] ?? r.data.length),
    })),
    placeholderData: previo => previo,
  })
  const subs = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / SMALL_PAGE_SIZE))

  return (
    <Modal open title={`${t('public_forms.submissions_title')} — ${form.name}`} onClose={onClose} width={700}>
      {isLoading ? <Spinner /> : subs.length === 0 ? (
        <EmptyState icon={<Inbox size={28} />} title={t('public_forms.no_submissions')} description={t('public_forms.no_submissions_subtitle')} />
      ) : (
        <div className="pubf-box">
          <Table
            data={subs}
            columns={[
              { key: 'submitted_at', label: t('public_forms.col_date'), render: (_v, s) => (
                <span className="u-text2-sm">
                  {fmtDate(s.submitted_at)}
                </span>
              ) },
              { key: 'submitter_name', label: t('public_forms.col_sender'), render: (_v, s) => s.submitter_name || s.submitter_email || '—' },
              { key: 'subject', label: t('public_forms.col_subject'), render: (_v, s) => <span className="pubf-box-2">{s.subject}</span> },
              { key: 'priority', label: t('public_forms.col_priority'), render: (_v, s) => <span className="u-text2">{s.priority ? (['low', 'medium', 'high', 'critical'].includes(s.priority) ? t(`public_forms.priority_${s.priority}`) : s.priority) : '—'}</span> },
              { key: 'created_entity_id', label: t('public_forms.col_ticket'), render: (_v, s) => <span className="pubf-text-accent-sm">{s.created_entity_id ? `#${String(s.created_entity_id).slice(0, 8)}` : '—'}</span> },
            ]}
          />
          <Pagination page={page} totalPages={totalPages} onChange={setPage} total={total} pageSize={SMALL_PAGE_SIZE} />
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

  const { data: forms = [], isLoading } = useQuery({
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
    <PageShell>
      <PageHeader
        icon={<FileText size={18} />}
        title={t('nav.public_forms')}
        subtitle={t('public_forms.subtitle')}
        actions={
          <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('public_forms.new_form')}</Button>
        }
      />

      {isLoading ? <Spinner /> : forms.length === 0 ? (
        <EmptyState
          icon={<FileText size={28} />}
          title={t('public_forms.empty_title')}
          description={t('public_forms.empty_subtitle')}
          ctaLabel={t('public_forms.new_form')} onCta={() => setShowCreate(true)}
        />
      ) : (
        <div className="pubf-lista">
          {forms.map(form => (
            <Card className="pubf-tarjeta" key={form.id}>
              <div className="pubf-tarjeta__info">
                <div className="pubf-tarjeta__cabecera">
                  <span className="pubf-tarjeta__nombre">{form.name}</span>
                  <StatusBadge kind={form.is_active ? 'success' : 'neutral'} dot caps={false}>{form.is_active ? t('public_forms.status_active') : t('public_forms.status_inactive')}</StatusBadge>
                  <span className="pubf-tipo">
                    {form.form_type === 'ticket' ? <Ticket size={13} aria-hidden /> : <CheckSquare size={13} aria-hidden />}
                    {form.form_type === 'ticket' ? t('public_forms.type_ticket') : t('public_forms.type_task')}
                  </span>
                </div>
                {form.description && (
                  <div className="pubf-tarjeta__desc">{form.description}</div>
                )}
                <div className="pubf-url">
                  {getPublicUrl(form.token)}
                </div>
                <div className="pubf-envios">
                  {t('public_forms.submissions_received').replace('{n}', String(form.submission_count || 0))}
                </div>
              </div>
              <div className="u-wrap-8">
                <Button size="sm" variant="secondary" icon={<Link2 size={13} />} onClick={() => copyLink(form.token)}>{t('public_forms.copy_link')}</Button>
                <Button size="sm" variant="secondary" icon={<Code2 size={13} />} title={t('public_forms.copy_widget_help')}
                  onClick={() => copyLink(form.token, getWidgetCode(form.token), t('public_forms.widget_copied'))}>{t('public_forms.copy_widget')}</Button>
                <Button size="sm" variant="secondary" icon={<Inbox size={13} />} onClick={() => setViewSubs(form)}>{t('public_forms.submissions')}</Button>
                <Button size="sm" variant="secondary" icon={<Pencil size={13} />} onClick={() => setEditing(form)}>{t('public_forms.edit_form')}</Button>
                <Button size="sm" variant="danger" icon={<Trash2 size={13} />} onClick={() =>
                  openConfirmGlobal({
                    title: t('public_forms.delete_form'),
                    message: t('public_forms.delete_confirm').replace('{name}', form.name),
                    onConfirm: () => deleteForm(form.id),
                  })
                }>{t('common.delete')}</Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {showCreate && <FormModal onClose={() => setShowCreate(false)} />}
      {editing && <FormModal form={editing} onClose={() => setEditing(null)} />}
      {viewSubs && <SubmissionsModal form={viewSubs} onClose={() => setViewSubs(null)} />}
    </PageShell>
  )
}
