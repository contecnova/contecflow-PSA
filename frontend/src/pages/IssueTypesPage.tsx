import type { CSSProperties } from 'react'
import { CHART_COLORS_EXTENDED, alpha } from '../constants/theme'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useState } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, issueTypesApi, customFieldsApi } from '../services/api'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Tag } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

interface ProjectItem {
  id: string | number
  name?: string
}

interface CustomFieldItem {
  field_key: string
  name: string
}

interface IssueTypeItem {
  id: string | number
  name: string
  value: string
  icon?: string
  color: string
  description?: string
  is_subtask?: boolean
  sort_order?: number
  field_keys?: string[]
}

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

const ps: CSSProperties = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is: CSSProperties = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const COLORS = CHART_COLORS_EXTENDED

const _DEP_TYPE_LABELS = {
  blocks:'Bloquea',blocked_by:'Bloqueada por',relates_to:'Relacionada',duplicates:'Duplica',cloned_from:'Clonada de'
}

function IssueTypeForm({ projectId, type, customFields, onClose }: { projectId: string; type: IssueTypeItem | null; customFields: CustomFieldItem[]; onClose: () => void }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!type?.id
  const autoValue = (n: string) => n.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'')
  const [form, setForm] = useState<IssueTypeFormState>({
    name:       type?.name        || '',
    value:      type?.value       || autoValue(type?.name || ''),
    icon:       type?.icon        || '',
    color:      type?.color       || '#7a8aaa',
    description:type?.description || '',
    is_subtask: type?.is_subtask  || false,
    sort_order: type?.sort_order  || 0,
    field_keys: type?.field_keys  || [],
  })
  const set = <K extends keyof IssueTypeFormState>(k: K) => (v: IssueTypeFormState[K]) => setForm((f) => ({...f, [k]: v}))

  const { mutate, isPending } = useMutation({
    mutationFn: (d: IssueTypeFormState) => isEdit
      ? issueTypesApi.update(projectId, type.id, d).then(r => r.data)
      : issueTypesApi.create(projectId, d).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['issue-types', projectId] })
      toast.success(isEdit ? t('issue_types.saved_ok') : t('issue_types.created_ok'))
      onClose()
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('issue_types.error_save'))),
  })

  const toggleField = (key: string) => {
    set('field_keys')(form.field_keys.includes(key)
      ? form.field_keys.filter(k => k !== key)
      : [...form.field_keys, key])
  }

  return (
    <Modal open onClose={onClose} title={isEdit ? t('issue_types.edit_modal_title') : t('issue_types.new_modal_title')}>
      <div style={{display:'flex',flexDirection:'column',gap:14}}>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
          <div>
            <label style={ls}>{t('issue_types.name')}</label>
            <input style={is} value={form.name} onChange={e => {
              const n = e.target.value
              setForm(f => ({...f, name:n, value: isEdit ? f.value : autoValue(n)}))
            }} />
          </div>
          <div>
            <label style={ls}>{t('issue_types.value_internal')}</label>
            <input style={{...is, fontFamily:'var(--font-mono)', fontSize: "var(--text-sm)"}} value={form.value}
              onChange={e => set('value')(e.target.value)} disabled={isEdit}
            />
          </div>
        </div>
        <div style={{display:'grid',gridTemplateColumns:'80px 1fr',gap:12}}>
          <div>
            <label style={ls}>{t('issue_types.icon')}</label>
            <input style={{...is, textAlign:'center', fontSize: "var(--text-xl)"}} value={form.icon}
              onChange={e => set('icon')(e.target.value)} />
          </div>
          <div>
            <label style={ls}>{t('issue_types.color')}</label>
            <div style={{display:'flex',gap:8,flexWrap:'wrap',paddingTop:4}}>
              {COLORS.map(c => (
                <button key={c} onClick={() => set('color')(c)}
                  style={{width:28,height:28,borderRadius:'50%',background:c,border:form.color===c?'3px solid #fff':'2px solid transparent',cursor:'pointer'}} />
              ))}
              <input type="color" value={/^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : '#7a8aaa'} onChange={e => set('color')(e.target.value)}
                style={{width:28,height:28,borderRadius:'50%',border:'none',cursor:'pointer',padding:0}} />
            </div>
          </div>
        </div>
        <div>
          <label style={ls}>{t('issue_types.description')}</label>
          <input style={is} value={form.description} onChange={e => set('description')(e.target.value)} />
        </div>
        <label style={{display:'flex',alignItems:'center',gap:8,cursor:'pointer',fontSize: "var(--text-base)"}}>
          <input type="checkbox" checked={form.is_subtask} onChange={e => set('is_subtask')(e.target.checked)} />
          {t('issue_types.subtask_checkbox')}
        </label>
        {customFields.length > 0 && (
          <div>
            <label style={ls}>{t('issue_types.required_fields_label')}</label>
            <div style={{display:'flex',flexWrap:'wrap',gap:8}}>
              {customFields.map(f => (
                <label key={f.field_key} style={{display:'flex',alignItems:'center',gap:6,cursor:'pointer',
                  padding:'4px 10px',borderRadius:6,border:`1px solid ${form.field_keys.includes(f.field_key)?'var(--accent-glow)':'var(--surface-4)'}`,
                  background:form.field_keys.includes(f.field_key)?'var(--accent-muted)':'transparent',fontSize: "var(--text-sm)"}}>
                  <input type="checkbox" checked={form.field_keys.includes(f.field_key)}
                    onChange={() => toggleField(f.field_key)} style={{margin:0}} />
                  {f.name}
                </label>
              ))}
            </div>
          </div>
        )}
        <div style={{display:'flex',justifyContent:'flex-end',gap:10,marginTop:8}}>
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
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [project, setProject] = useState<string>('')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<IssueTypeItem | null>(null)

  const { data: projectsRaw = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })
  const projects = projectsRaw as ProjectItem[]
  const { data: typesRaw = [], isLoading } = useQuery({
    queryKey: ['issue-types', project],
    queryFn: () => issueTypesApi.list(project).then(r => r.data?.items ?? r.data ?? []).catch(() => []),
    enabled: !!project,
  })
  const types = typesRaw as IssueTypeItem[]
  const { data: customFieldsRaw = [] } = useQuery({
    queryKey: ['custom-fields', project],
    queryFn: () => customFieldsApi.list(project).then(r => r.data).catch(() => []),
    enabled: !!project,
  })
  const customFields = customFieldsRaw as CustomFieldItem[]

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
        actions={project && types.length > 0 && (
          <Button onClick={() => { setEditing(null); setShowForm(true) }}>{`+ ${t('issue_types.new_type')}`}</Button>
        )} />

      <div style={{...ps, marginBottom:20}}>
        <label style={ls}>{t('issue_types.project_label')}</label>
        <select value={project} onChange={e => setProject(e.target.value)} style={{...is, width:360}}>
          <option value="">{t('issue_types.select_project_option')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!project && <EmptyState icon="🏷" title={t('issue_types.select_project_title')} description={t('issue_types.select_project_desc')} />}
      {project && isLoading && <Spinner />}

      {project && !isLoading && types.length === 0 && (
        <div style={{...ps, textAlign:'center', padding:'48px 24px'}}>
          <div style={{fontSize: "var(--text-6xl)", marginBottom:16}}>🏷</div>
          <div style={{fontSize: "var(--text-md-em)", fontWeight:600, marginBottom:8}}>{t('issue_types.no_types')}</div>
          <div style={{fontSize: "var(--text-base)", color:'var(--text-2)', marginBottom:24}}>{t('issue_types.no_types_desc')}</div>
          <div style={{display:'flex', gap:12, justifyContent:'center'}}>
            <Button onClick={() => initTypes()} disabled={initing}>
              {initing ? t('issue_types.initializing') : t('issue_types.init_standard')}
            </Button>
            <Button variant="secondary" onClick={() => { setEditing(null); setShowForm(true) }}>
              {t('issue_types.create_custom')}
            </Button>
          </div>
        </div>
      )}

      {project && types.length > 0 && (
        <div>
          {/* Resumen visual */}
          <div style={{display:'flex', gap:10, flexWrap:'wrap', marginBottom:20}}>
            {types.map(typeItem => (
              <div key={typeItem.id} style={{background:'var(--surface-2)', border:`1px solid ${alpha(typeItem.color, '40')}`,
                borderRadius:10, padding:'12px 16px', minWidth:120, textAlign:'center'}}>
                <div style={{fontSize: "var(--text-3xl)", marginBottom:4}}>{typeItem.icon || '📌'}</div>
                <div style={{fontWeight:600, fontSize: "var(--text-base)", color:typeItem.color}}>{typeItem.name}</div>
                <div style={{fontSize: "var(--text-xs)", color:'var(--text-3)', fontFamily:'var(--font-mono)'}}>{typeItem.value}</div>
                {typeItem.is_subtask && <div style={{fontSize: "var(--text-2xs)", color:'var(--text-2)', marginTop:4}}>{t('issue_types.subtask')}</div>}
              </div>
            ))}
          </div>
          {/* Tabla detallada */}
          <div style={ps}>
            <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16}}>
              <div style={{fontSize: "var(--text-md)", fontWeight:600}}>{t('issue_types.types_count').replace('{n}', String(types.length))}</div>
              <Button onClick={() => { setEditing(null); setShowForm(true) }}>{t('issue_types.new_type')}</Button>
            </div>
            <table style={{width:'100%', borderCollapse:'collapse', fontSize: "var(--text-base)"}}>
              <thead>
                <tr style={{borderBottom:'1px solid var(--surface-4)'}}>
                  {[t('issue_types.type'), t('issue_types.value'), t('issue_types.description'), t('issue_types.subtask'), t('issue_types.required_fields'), t('issue_types.actions')].map(h => (
                    <th key={h} style={{textAlign:'left', padding:'8px 12px', fontSize: "var(--text-xs)", color:'var(--text-2)',
                      textTransform:'uppercase', letterSpacing:'.06em'}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {types.map((typeItem, i) => (
                  <tr key={typeItem.id} style={{borderBottom:'1px solid #1e2d45', background:i%2===0?'transparent':'rgba(255,255,255,0.02)'}}>
                    <td style={{padding:'10px 12px'}}>
                      <div style={{display:'flex', alignItems:'center', gap:10}}>
                        <div style={{width:32, height:32, borderRadius:8, background:alpha(typeItem.color, '20'),
                          display:'flex', alignItems:'center', justifyContent:'center', fontSize: "var(--text-lg)"}}>
                          {typeItem.icon || '📌'}
                        </div>
                        <span style={{fontWeight:600, color:typeItem.color}}>{typeItem.name}</span>
                      </div>
                    </td>
                    <td style={{padding:'10px 12px', fontFamily:'var(--font-mono)', fontSize: "var(--text-xs)", color:'var(--text-2)'}}>{typeItem.value}</td>
                    <td style={{padding:'10px 12px', color:'var(--text-2)', fontSize: "var(--text-sm)", maxWidth:220}}>
                      {typeItem.description || '—'}
                    </td>
                    <td style={{padding:'10px 12px'}}>
                      <span style={{color: typeItem.is_subtask ? 'var(--success)' : 'var(--text-3)', fontSize: "var(--text-base)"}}>
                        {typeItem.is_subtask ? '✓' : '—'}
                      </span>
                    </td>
                    <td style={{padding:'10px 12px', fontSize: "var(--text-sm)", color:'var(--text-2)'}}>
                      {typeItem.field_keys && typeItem.field_keys.length > 0 ? typeItem.field_keys.join(', ') : '—'}
                    </td>
                    <td style={{padding:'10px 12px'}}>
                      <div style={{display:'flex', gap:8}}>
                        <button onClick={() => { setEditing(typeItem); setShowForm(true) }}
                          style={{background:'none', border:'1px solid var(--surface-4)', borderRadius:6,
                            padding:'4px 10px', color:'var(--text-2)', cursor:'pointer', fontSize: "var(--text-xs)"}}>
                          {t('issue_types.edit')}
                        </button>
                        <button onClick={() => { openConfirmGlobal({ message: t('issue_types.confirm_delete').replace('{name}', typeItem.name), onConfirm: () => deleteType(typeItem.id), danger: true }) }}
                          style={{background:'none', border:'1px solid var(--danger-border)', borderRadius:6,
                            padding:'4px 10px', color:'var(--danger)', cursor:'pointer', fontSize: "var(--text-xs)"}}>
                          {t('issue_types.delete')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{marginTop:20, padding:'12px 16px', background:'var(--surface-1)', borderRadius:8,
              border:'1px solid #1e2d45', fontSize: "var(--text-sm)", color:'var(--text-3)', lineHeight:1.7}}>
              <strong style={{color:'var(--text-2)'}}>{t('issue_types.how_to_use')}</strong> {t('issue_types.how_to_use_desc')}
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
