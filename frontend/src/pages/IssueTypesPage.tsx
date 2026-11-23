import type { CSSProperties } from 'react'
import { CHART_COLORS_EXTENDED, COLOR_DATO_POR_DEFECTO, alpha } from '../constants/theme'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useState, useId } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { issueTypesApi, customFieldsApi } from '../services/api'
import { useListaDeProyectos } from '../hooks/useListas'
import type { CampoPersonalizado, TipoDeIncidencia } from '../services/api/tipos-rendimiento'
import { Button, Spinner, EmptyState, Modal, Pulsable, Select, TablaSimple, Checkbox, useErroresDeCampo, Input, EstadoDeError } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Pencil, Plus, Tag, Trash2, Wand2 } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import './IssueTypesPage.css'

type IssueTypeItem = TipoDeIncidencia

interface IssueTypeFormState {
  name: string
  value: string
  icon: string
  color: string
  description: string
  is_subtask: boolean
  sort_order: number
  field_keys: string[]
}


const COLORS = CHART_COLORS_EXTENDED

function IssueTypeForm({ projectId, type, customFields, onClose }: { projectId: string; type: IssueTypeItem | null; customFields: CampoPersonalizado[]; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!type?.id
  const autoValue = (n: string) => n.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'')
  const [form, setForm] = useState<IssueTypeFormState>({
    name:       type?.name        || '',
    value:      type?.value       || autoValue(type?.name || ''),
    icon:       type?.icon        || '',
    color:      type?.color       || COLOR_DATO_POR_DEFECTO,
    description:type?.description || '',
    is_subtask: type?.is_subtask  || false,
    sort_order: type?.sort_order  || 0,
    field_keys: type?.field_keys  || [],
  })
  const set = <K extends keyof IssueTypeFormState>(k: K) => (v: IssueTypeFormState[K]) => setForm((f) => ({...f, [k]: v}))

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (d: IssueTypeFormState) => isEdit
      ? issueTypesApi.update(projectId, type.id, d).then(r => r.data)
      : issueTypesApi.create(projectId, d).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['issue-types', projectId] })
      toast.success(isEdit ? t('issue_types.saved_ok') : t('issue_types.created_ok'))
      onClose()
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('issue_types.error_save'))) },
  })

  const toggleField = (key: string) => {
    set('field_keys')(form.field_keys.includes(key)
      ? form.field_keys.filter(k => k !== key)
      : [...form.field_keys, key])
  }

  return (
    <Modal open onClose={onClose} title={isEdit ? t('issue_types.edit_modal_title') : t('issue_types.new_modal_title')}>
      <div className="u-stack-14">
        <div className="u-grid2-12">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="issue-types-page-e9">{t('issue_types.name')}</label>
            <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => {
              const n = e.target.value
              setForm(f => ({...f, name:n, value: isEdit ? f.value : autoValue(n)}))
            }} inputClassName="issue-types-page-e10" />{msg('name')}
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="issue-types-page-e9">{t('issue_types.value_internal')}</label>
            <Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.value} onChange={e => set('value')(e.target.value)} disabled={isEdit} inputClassName="ds-codigo issue-types-page-e1" />{msg('value')}
          </div>
        </div>
        <div className="ityp-grid">
          <div>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="issue-types-page-e9">{t('issue_types.icon')}</label>
            <Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.icon} onChange={e => set('icon')(e.target.value)} inputClassName="issue-types-page-e2" />{msg('icon')}
          </div>
          <div>
            <label className="issue-types-page-e9">{t('issue_types.color')}</label>
            <div className="ityp-row">
              {COLORS.map(c => (
                <Pulsable key={c} aria-label={`${t('issue_types.color')} ${c}`} aria-pressed={form.color===c} onClick={() => set('color')(c)}
                  className={`ityp-btn issuetyp-sx1 ${form.color===c ? 'issuetyp-sx2' : 'issuetyp-sx3'} issue-types-page-e3`} style={{ '--issue-types-page-background': c } as CSSProperties}><span aria-hidden="true" /></Pulsable>
              ))}
              <input type="color" aria-label={t('issue_types.color')} value={/^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : COLOR_DATO_POR_DEFECTO} onChange={e => set('color')(e.target.value)}
                className="ityp-input" />
            </div>
          </div>
        </div>
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="issue-types-page-e9">{t('issue_types.description')}</label>
          <Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.description} onChange={e => set('description')(e.target.value)} inputClassName="issue-types-page-e10" />{msg('description')}
        </div>
        <label className="u-row-center-8-pointer">
          <Checkbox aria-label={t('issue_types.subtask_checkbox')} checked={form.is_subtask} onChange={(_, e) => set('is_subtask')(e.target.checked)} />
          {t('issue_types.subtask_checkbox')}
        </label>
        {customFields.length > 0 && (
          <div>
            <label className="issue-types-page-e9">{t('issue_types.required_fields_label')}</label>
            <div className="u-wrap-8">
              {customFields.map(f => (
                <label key={f.field_key} className={`ityp-label issuetyp-sx4 ${form.field_keys.includes(f.field_key) ? 'issuetyp-sx5' : 'issuetyp-sx6'} issue-types-page-e4`} style={{ '--issue-types-page-border': `1px solid ${form.field_keys.includes(f.field_key)?'var(--accent-glow)':'var(--surface-4)'}` } as CSSProperties}>
                  <Checkbox aria-label={f.name} checked={form.field_keys.includes(f.field_key)}
                    onChange={() => toggleField(f.field_key)} className="ityp-input-2" />
                  {f.name}
                </label>
              ))}
            </div>
          </div>
        )}
        <div className="ityp-row-2">
          <Button variant="secondary" onClick={onClose}>{t('issue_types.cancel')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.name || (!isEdit && !form.value)} loading={isPending}>
            {isPending ? t('issue_types.saving') : isEdit ? t('issue_types.save_changes') : t('issue_types.create_type')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function IssueTypesPage(): JSX.Element {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [project, setProject] = useState<string>('')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<IssueTypeItem | null>(null)

  // 23-11-2026 (04 A8 / M6): lista compartida de proyectos y sin `.catch` tragados (avisa el onError global;
  // la lista de tipos, además, pinta el estado de error con reintento).
  const { data: projects = [] } = useListaDeProyectos()
  const { data: types = [], isLoading, error: errorTipos, refetch: refetchTipos } = useQuery({
    queryKey: ['issue-types', project],
    queryFn: () => issueTypesApi.list(project).then(r => r.data),
    enabled: !!project,
  })
  const { data: customFields = [] } = useQuery({
    queryKey: ['custom-fields', project],
    queryFn: () => customFieldsApi.list(project).then(r => r.data),
    enabled: !!project,
  })

  const { mutate: initTypes, isPending: initing } = useMutation({
    mutationFn: () => issueTypesApi.init(project).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['issue-types', project] })
      toast.success(t('issue_types.init_ok'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('issue_types.error_init'))),
  })
  const { mutate: deleteType } = useMutation({
    mutationFn: (id: string | number) => issueTypesApi.delete(project, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['issue-types', project] })
      toast.success(t('issue_types.deleted_ok'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('issue_types.error_delete'))),
  })

  return (
    <PageShell>
      <PageHeader icon={<Tag size={18} />} title={t('issue_types.title')} subtitle={t('issue_types.subtitle')}
        actions={project ? (
          <Button icon={<Plus size={14} />} onClick={() => { setEditing(null); setShowForm(true) }}>{t('issue_types.new_type')}</Button>
        ) : undefined} />

      <div className="issue-types-page-e5">
        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="issue-types-page-e9">{t('issue_types.project_label')}</label>
        <Select suelto placeholder={false} id={`${idCampo}-1`} value={project} onChange={e => setProject(e.target.value)} className="issue-types-page-e6">
          <option value="">{t('issue_types.select_project_option')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
      </div>

      {!project && <EmptyState icon={<Tag size={28} />} title={t('issue_types.select_project_title')} description={t('issue_types.select_project_desc')} />}
      {project && isLoading && <Spinner />}

      {project && errorTipos && <EstadoDeError error={errorTipos} onReintentar={() => { void refetchTipos() }} />}

      {project && !isLoading && !errorTipos && types.length === 0 && (
        <EmptyState icon={<Tag size={28} />} title={t('issue_types.no_types')} description={t('issue_types.no_types_desc')}
          action={
            <div className="ityp-row-3">
              <Button icon={<Wand2 size={14} />} onClick={() => initTypes()} loading={initing}>
                {initing ? t('issue_types.initializing') : t('issue_types.init_standard')}
              </Button>
              <Button variant="secondary" icon={<Plus size={14} />} onClick={() => { setEditing(null); setShowForm(true) }}>
                {t('issue_types.new_type')}
              </Button>
            </div>
          } />
      )}

      {project && types.length > 0 && (
        <div>
          {/* Resumen visual */}
          <div className="ityp-row-4">
            {types.map(typeItem => (
              <div key={typeItem.id} className="ityp-box-3 issuetyp-sx7 issue-types-page-e4" style={{ '--issue-types-page-border': `1px solid ${alpha(typeItem.color, '40')}` } as CSSProperties}>
                <div className="ityp-box-4">{typeItem.icon || <Tag size={18} aria-hidden />}</div>
                <div className="u-base-600 issue-types-page-e8" style={{ '--issue-types-page-color': typeItem.color } as CSSProperties}>{typeItem.name}</div>
                <div className="u-text3-mono-xs">{typeItem.value}</div>
                {typeItem.is_subtask && <div className="ityp-box-5">{t('issue_types.subtask')}</div>}
              </div>
            ))}
          </div>
          {/* Tabla detallada */}
          <div className="issue-types-page-e11">
            <div className="u-row-between-mb16">
              <div className="u-md-600">{t('issue_types.types_count').replace('{n}', String(types.length))}</div>
            </div>
            <TablaSimple claseTabla="ityp-table">
              <thead>
                <tr className="u-border-b">
                  {[t('issue_types.type'), t('issue_types.value'), t('issue_types.description'), t('issue_types.subtask'), t('issue_types.required_fields'), t('issue_types.actions')].map(h => (
                    <th key={h} className="ityp-th">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {types.map((typeItem, i) => (
                  <tr key={typeItem.id} className={`ityp-row-5 ${i%2===0 ? 'issuetyp-sx6' : 'issuetyp-sx8'}`}>
                    <td className="u-pad-10-12" aria-labelledby={`${idCampo}-${typeItem.id}-n`}>
                      <div className="u-row-center-10">
                        <div className="ityp-row-6 issue-types-page-e3" style={{ '--issue-types-page-background': alpha(typeItem.color, '20') } as CSSProperties}>
                          {typeItem.icon || <Tag size={14} aria-hidden />}
                        </div>
                        <span id={`${idCampo}-${typeItem.id}-n`} className="u-600 issue-types-page-e8" style={{ '--issue-types-page-color': typeItem.color } as CSSProperties}>{typeItem.name}</span>
                      </div>
                    </td>
                    <td className="ityp-td"><code className="ds-codigo">{typeItem.value}</code></td>
                    <td className="ityp-td-2">
                      {typeItem.description || '—'}
                    </td>
                    <td className="u-pad-10-12">
                      <span className={`ityp-label-2 ${typeItem.is_subtask ? 'issuetyp-sx9' : 'issuetyp-sx10'}`}>
                        {typeItem.is_subtask ? '✓' : '—'}
                      </span>
                    </td>
                    <td className="ityp-td-3">
                      {typeItem.field_keys && typeItem.field_keys.length > 0
                        ? typeItem.field_keys.map(k => customFields.find(f => f.field_key === k)?.name || k).join(', ')
                        : '—'}
                    </td>
                    <td className="u-pad-10-12" aria-label={t('issue_types.actions')}>
                      <div className="u-row-8">
                        <Button size="xs" variant="secondary" icon={<Pencil size={13} />} onClick={() => { setEditing(typeItem); setShowForm(true) }}>
                          {t('issue_types.edit')}
                        </Button>
                        <Button size="xs" variant="danger" icon={<Trash2 size={13} />} onClick={() => { openConfirmGlobal({ message: t('issue_types.confirm_delete').replace('{name}', typeItem.name), onConfirm: () => deleteType(typeItem.id), danger: true }) }}>
                          {t('issue_types.delete')}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </TablaSimple>
            <div className="ityp-card">
              <strong className="u-text2">{t('issue_types.how_to_use')}</strong> {t('issue_types.how_to_use_desc')}
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <IssueTypeForm projectId={project} type={editing} customFields={customFields}
          onClose={() => { setShowForm(false); setEditing(null) }} />
      )}
    </PageShell>
  )
}
