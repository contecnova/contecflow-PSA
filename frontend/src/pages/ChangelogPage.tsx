/**
 * ChangelogPage — Release notes y changelog por proyecto
 * Genera automáticamente entradas desde tareas completadas o permite añadirlas manualmente.
 */
import { useState, useId, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import api, { projectsApi } from '../services/api'
import { Spinner, EmptyState, Button, Modal, Tabs, IconButton, Select, useErroresDeCampo, Input, Textarea } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Bug, Flag, Plus, ScrollText, Sparkles, Trash2, TriangleAlert, Wand2, Zap, type LucideIcon } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { extractErr, fmtDate } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import { useFormValidation } from '../hooks/useFormValidation'
import { openConfirmGlobal } from '../context/ConfirmContext'
import DateInput from '../components/ui/DateInput'
import './ChangelogPage.css'

type EntryType = 'feature' | 'bugfix' | 'improvement' | 'milestone' | 'breaking'
type TFn = ReturnType<typeof useAppT>

interface ProjectItem {
  id: string | number
  code?: string
  name?: string
}

interface AuthorInfo {
  full_name?: string
}

interface ChangelogEntry {
  id: string | number
  version_tag?: string
  entry_date?: string
  entry_type?: EntryType
  is_auto_generated?: boolean
  title?: string
  description?: string
  author?: AuthorInfo | null
}

interface ChangelogResponse {
  entries?: ChangelogEntry[]
}

interface GenerateResult {
  generated: number
  period_weeks?: number
  message?: string
}

interface ManualEntryPayload {
  version_tag?: string
  entry_date: string
  entry_type: EntryType
  title: string
  description?: string
}

interface GeneratePayload {
  weeks: number
  version_tag?: string
}

function getTypeMeta(t: TFn): Record<EntryType, { label: string; Icon: LucideIcon }> {
  return {
    feature:     { label: t('changelog.type_feature'),     Icon: Sparkles },
    bugfix:      { label: t('changelog.type_bugfix'),      Icon: Bug },
    improvement: { label: t('changelog.type_improvement'), Icon: Zap },
    milestone:   { label: t('changelog.type_milestone'),   Icon: Flag },
    breaking:    { label: t('changelog.type_breaking'),    Icon: TriangleAlert },
  }
}

const manualEntrySchema = (t: TFn) => z.object({
  version_tag: z.string().optional(),
  entry_date: z.string().min(1, t('changelog.err_date_required')),
  entry_type: z.enum(['feature', 'bugfix', 'improvement', 'milestone', 'breaking']),
  title: z.string().trim().min(1, t('changelog.err_title_required')),
  description: z.string().optional(),
})

const generateSchema = (t: TFn) => z.object({
  weeks: z.coerce.number().int(t('changelog.err_weeks_int')).min(1, t('changelog.err_weeks_min')).max(52, t('changelog.err_weeks_max')),
  version_tag: z.string().optional(),
})

function EntryCard({ entry, onDelete }: { entry: ChangelogEntry; onDelete: (id: string | number) => void }) {
  const t = useAppT()
  const typeMeta = getTypeMeta(t)
  const tipo: EntryType = entry.entry_type && typeMeta[entry.entry_type] ? entry.entry_type : 'feature'
  const meta = typeMeta[tipo]
  return (
    <div className="chl-card">
      <div className={`chl-card-icon chl-type--${tipo}`} aria-hidden="true"><meta.Icon size={16} /></div>
      <div className="u-flex1-min0">
        <div className="chl-card-head">
          <div className="u-min0">
            <div className="chl-card-tags">
              {entry.version_tag && (
                <span className="chl-version">{entry.version_tag}</span>
              )}
              <span className={`chl-type-badge chl-type--${tipo}`}>{meta.label}</span>
              {entry.is_auto_generated && (
                <span className="chl-auto">{t('changelog.auto')}</span>
              )}
            </div>
            <div className="chl-card-title">{entry.title}</div>
          </div>
          <div className="chl-card-side">
            <span className="u-text3-xs">{entry.entry_date ? fmtDate(entry.entry_date) : ''}</span>
            <IconButton onClick={() => onDelete(entry.id)} className="chl-delete"
              ariaLabel={t('changelog.delete_entry')}><Trash2 size={14} /></IconButton>
          </div>
        </div>
        {entry.description && (
          <div className="chl-card-desc">{entry.description}</div>
        )}
        {entry.author && (
          <div className="chl-card-author">{t('changelog.by_author', {author: entry.author.full_name})}</div>
        )}
      </div>
    </div>
  )
}

function ManualEntryModal({ projectId, onClose, onSaved }: { projectId: string; onClose: () => void; onSaved: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const typeMeta = getTypeMeta(t)
  const today = new Date().toISOString().split('T')[0]
  const [form, setForm] = useState<ManualEntryPayload>({ version_tag: '', entry_date: today, entry_type: 'feature', title: '', description: '' })
  const schema = useMemo(() => manualEntrySchema(t), [t])
  const validation = useFormValidation(schema)

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate: save, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (data: ManualEntryPayload) => api.post(`/projects/${projectId}/changelog`, data),
    onSuccess: () => { validation.setErrors({}); onSaved(); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('changelog.err_save'))) },
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success || !result.data) return
    save(result.data as ManualEntryPayload)
  }

  return (
    <div className="u-stack-14">
      <div className="chl-grid3">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="chl-label">{t('changelog.version_tag')}</label>
          <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.version_tag} onChange={e => { setForm(f => ({ ...f, version_tag: e.target.value })); validation.clearFieldError('version_tag') }} aria-invalid={!!validation.errors.version_tag} placeholder={t('changelog.version_tag_ph')} inputClassName="chl-input" />{msg('version_tag')}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="chl-label">{t('changelog.date')}</label>
          <DateInput id={`${idCampo}-2`} value={form.entry_date} onChange={e => { setForm(f => ({ ...f, entry_date: e.target.value })); validation.clearFieldError('entry_date') }} className="chl-input" aria-invalid={!!validation.errors.entry_date} />{msg('entry_date')}
          {validation.errors.entry_date && <p className="u-field-error">{validation.errors.entry_date}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="chl-label">{t('changelog.type')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.entry_type} onChange={e => { setForm((f) => ({ ...f, entry_type: e.target.value as EntryType })); validation.clearFieldError('entry_type') }} className="chl-input" aria-invalid={!!validation.errors.entry_type}>
            {Object.entries(typeMeta).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </Select>{msg('entry_type')}
        </div>
      </div>
      <div>
        <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="chl-label">{t('changelog.title_label')}</label>
        <Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.title} onChange={e => { setForm(f => ({ ...f, title: e.target.value })); validation.clearFieldError('title') }} aria-invalid={!!validation.errors.title} placeholder={t('changelog.title_ph')} inputClassName="chl-input" />{msg('title')}
        {validation.errors.title && <p className="u-field-error">{validation.errors.title}</p>}
      </div>
      <div>
        <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="chl-label">{t('changelog.description')}</label>
        <Textarea id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.description} onChange={e => { setForm(f => ({ ...f, description: e.target.value })); validation.clearFieldError('description') }} rows={3} aria-invalid={!!validation.errors.description} placeholder={t('changelog.description_ph')} inputClassName="chl-input" />{msg('description')}
      </div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{t('changelog.cancel')}</Button>
        <Button onClick={submit} disabled={isPending}>{isPending ? t('changelog.saving') : t('changelog.add_entry')}</Button>
      </div>
    </div>
  )
}

function GenerateModal({ projectId, onClose, onSaved }: { projectId: string; onClose: () => void; onSaved: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const [weeks, setWeeks] = useState(2)
  const [versionTag, setVersionTag] = useState('')
  const schema = useMemo(() => generateSchema(t), [t])
  const validation = useFormValidation(schema)

  const [genResult, setGenResult] = useState<GenerateResult | null>(null)

  const { mutate: generate, isPending } = useMutation({
    mutationFn: ({ weeks: validWeeks, version_tag }: GeneratePayload) => api.post(`/projects/${projectId}/changelog/generate`, { weeks: validWeeks, version_tag: version_tag || null }),
    onSuccess: (res) => { setGenResult(res.data as GenerateResult); onSaved() },
    onError: (e: unknown) => toast.error(extractErr(e, t('changelog.err_generate'))),
  })

  const submitGenerate = () => {
    const result = validation.validateForm({ weeks, version_tag: versionTag })
    if (!result.success || !result.data) return
    generate(result.data as GeneratePayload)
  }

  return (
    <div className="u-stack-14">
      <div className="chl-note chl-note--info">
        {t('changelog.generate_info')}
      </div>
      <div className="u-grid2-12">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="chl-label">{t('changelog.period_weeks')}</label>
          <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} type="number" value={weeks} onChange={e => { setWeeks(Number(e.target.value)); validation.clearFieldError('weeks') }} min={1} max={52} aria-invalid={!!validation.errors.weeks} inputClassName="chl-input" />
          {validation.errors.weeks && <p className="u-field-error">{validation.errors.weeks}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="chl-label">{t('changelog.version_tag_optional')}</label>
          <Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={versionTag} onChange={e => { setVersionTag(e.target.value); validation.clearFieldError('version_tag') }} aria-invalid={!!validation.errors.version_tag} placeholder={t('changelog.version_tag_ph')} inputClassName="chl-input" />
        </div>
      </div>
      {genResult && genResult.generated > 0 && (
        <div className="chl-note chl-note--ok" role="status">
          {t('changelog.generated_success', {count: genResult.generated, weeks: genResult.period_weeks})}
        </div>
      )}
      {genResult && genResult.generated === 0 && (
        <div className="chl-note chl-note--empty" role="status">
          {t('changelog.generated_empty', {message: genResult.message ?? ''})}
        </div>
      )}
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{genResult ? t('changelog.close') : t('changelog.cancel')}</Button>
        {!genResult && <Button onClick={submitGenerate} disabled={isPending}>{isPending ? t('changelog.generating') : t('changelog.generate')}</Button>}
      </div>
    </div>
  )
}

export default function ChangelogPage(): JSX.Element {
  const t = useAppT()
  const typeMeta = getTypeMeta(t)
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState('')
  const [typeFilter, setTypeFilter] = useState<'all' | EntryType>('all')
  const [showManual, setShowManual] = useState(false)
  const [showGenerate, setShowGenerate] = useState(false)

  const { data: projRaw = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then(r => r.data),
  })
  const projects = (Array.isArray(projRaw) ? projRaw : []) as ProjectItem[]

  const { data: changelogRaw, isLoading } = useQuery({
    queryKey: ['changelog', selectedProject],
    queryFn: () => api.get(`/projects/${selectedProject}/changelog`).then(r => r.data),
    enabled: !!selectedProject,
  })
  const changelog = (changelogRaw ?? null) as ChangelogResponse | null

  const { mutate: deleteEntry } = useMutation({
    mutationFn: (id: string | number) => api.delete(`/projects/${selectedProject}/changelog/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['changelog', selectedProject] }),
    onError: (e: unknown) => toast.error(extractErr(e, t('changelog.err_delete'))),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['changelog', selectedProject] })
  const allEntries = changelog?.entries || []
  // El filtro por tipo es local: así los contadores de cada pestaña no se
  // vacían al elegir una (antes se filtraba en el servidor).
  const entries = typeFilter === 'all' ? allEntries : allEntries.filter(e => e.entry_type === typeFilter)
  const typeTabs = [
    { id: 'all', label: t('changelog.all'), count: allEntries.length },
    ...Object.entries(typeMeta)
      .map(([k, v]) => ({ id: k, label: v.label, icon: <v.Icon size={14} />, count: allEntries.filter(e => e.entry_type === k).length }))
      .filter(x => x.count > 0),
  ]
  const addButton = (
    <Button icon={<Plus size={14} />} onClick={() => setShowManual(true)} disabled={!selectedProject}>{t('changelog.add_entry')}</Button>
  )

  return (
    <PageShell>
      <PageHeader
        title={t('nav.changelog')}
        subtitle={t('changelog.subtitle')}
        icon={<ScrollText size={18} />}
        showListExport={Boolean(selectedProject && entries.length)}
        exportTargetSelector='[data-export-table="changelog-list"]'
        exportFilePrefix='changelog'
        actions={<>
          <Button variant="secondary" icon={<Wand2 size={14} />} onClick={() => setShowGenerate(true)} disabled={!selectedProject}>{t('changelog.generate')}</Button>
          {addButton}
        </>}
      />

      <div className="ds-page">
        <div className="ds-toolbar">
          <Select suelto placeholder={false} value={selectedProject} onChange={e => { setSelectedProject(e.target.value); setTypeFilter('all') }}
            className="chl-project" aria-label={t('changelog.project_aria')}>
            <option value="">{t('changelog.select_project')}</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </Select>
        </div>

        {selectedProject && allEntries.length > 0 && (
          <Tabs items={typeTabs} active={typeFilter} onChange={id => setTypeFilter(id as 'all' | EntryType)} ariaLabel={t('changelog.filter_aria')} />
        )}

        {!selectedProject ? (
          <EmptyState icon={<ScrollText size={28} />} title={t('changelog.no_project_title')} description={t('changelog.no_project_desc')} />
        ) : isLoading ? (
          <div className="chl-loading" role="status"><Spinner /><span className="u-text2">{t('changelog.loading')}</span></div>
        ) : entries.length === 0 ? (
          <EmptyState icon={<ScrollText size={28} />} title={t('changelog.empty_title')}
            description={t('changelog.empty_desc')}
            action={addButton}
          />
        ) : (
          <div data-export-table="changelog-list" className="u-stack-10">
            {entries.map(e => <EntryCard key={e.id} entry={e} onDelete={(id) => openConfirmGlobal({ message: t('changelog.confirm_delete', { title: e.title ?? '' }), onConfirm: () => deleteEntry(id), danger: true })} />)}
          </div>
        )}
      </div>

      {showManual && (
        <Modal open title={t('changelog.add_entry')} onClose={() => setShowManual(false)} width={560}>
          <ManualEntryModal projectId={selectedProject} onClose={() => setShowManual(false)} onSaved={invalidate} />
        </Modal>
      )}

      {showGenerate && (
        <Modal open title={t('changelog.generate')} onClose={() => setShowGenerate(false)} width={500}>
          <GenerateModal projectId={selectedProject} onClose={() => setShowGenerate(false)} onSaved={invalidate} />
        </Modal>
      )}
    </PageShell>
  )
}
