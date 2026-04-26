/**
 * ChangelogPage — Release notes y changelog por proyecto
 * Genera automáticamente entradas desde tareas completadas o permite añadirlas manualmente.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import api, { projectsApi } from '../services/api'
import { Spinner, EmptyState, Button, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { ScrollText } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import { useFormValidation } from '../hooks/useFormValidation'

function getTypeMeta(t) {
  return {
    feature:     { label: t('changelog.type_feature'),      color: 'var(--accent)',   bg: 'rgba(79,142,247,0.12)',  icon: '✨' },
    bugfix:      { label: t('changelog.type_bugfix'),       color: 'var(--danger)',   bg: 'rgba(248,113,113,0.12)', icon: '🐛' },
    improvement: { label: t('changelog.type_improvement'),  color: 'var(--warning)',  bg: 'rgba(251,191,36,0.12)',  icon: '⚡' },
    milestone:   { label: t('changelog.type_milestone'),    color: 'var(--success)',  bg: 'rgba(74,222,128,0.12)',  icon: '🏆' },
    breaking:    { label: t('changelog.type_breaking'),     color: '#f97316',         bg: 'rgba(249,115,22,0.12)',  icon: '💥' },
  }
}

const inputStyle = {
  width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13,
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
}
const lbStyle = {
  fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase',
  display: 'block', marginBottom: 5,
}

const manualEntrySchema = z.object({
  version_tag: z.string().optional(),
  entry_date: z.string().min(1, 'La fecha es obligatoria'),
  entry_type: z.enum(['feature', 'bugfix', 'improvement', 'milestone', 'breaking']),
  title: z.string().trim().min(1, 'El titulo es obligatorio'),
  description: z.string().optional(),
})

const generateSchema = z.object({
  weeks: z.coerce.number().int('Debe ser un numero entero').min(1, 'Minimo 1 semana').max(52, 'Maximo 52 semanas'),
  version_tag: z.string().optional(),
})

function EntryCard({ entry, onDelete }) {
  const t = useAppT()
  const typeMeta = getTypeMeta(t)
  const meta = typeMeta[entry.entry_type] || typeMeta.feature
  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
      borderRadius: 12, padding: '14px 18px', display: 'flex', gap: 14,
    }}>
      <div style={{ fontSize: 22, flexShrink: 0, marginTop: 2 }}>{meta.icon}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6, gap: 10 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
              {entry.version_tag && (
                <span style={{ fontSize: 10, fontFamily: 'monospace', padding: '2px 7px', borderRadius: 8, background: 'var(--surface-4)', color: 'var(--text-2)', fontWeight: 700 }}>{entry.version_tag}</span>
              )}
              <span style={{ fontSize: 11, padding: '2px 9px', borderRadius: 20, background: meta.bg, color: meta.color, fontWeight: 700 }}>{meta.label}</span>
              {entry.is_auto_generated && (
                <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 10, background: 'var(--surface-3)', color: 'var(--text-3)' }}>{t('changelog.auto')}</span>
              )}
            </div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)' }}>{entry.title}</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{entry.entry_date}</span>
            <button onClick={() => onDelete(entry.id)}
              style={{ background: 'none', border: 'none', color: 'var(--text-4)', cursor: 'pointer', padding: '2px 4px', fontSize: 14, borderRadius: 4 }}
              title="Eliminar entrada">×</button>
          </div>
        </div>
        {entry.description && (
          <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5 }}>{entry.description}</div>
        )}
        {entry.author && (
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 8 }}>{t('changelog.by_author', {author: entry.author.full_name})}</div>
        )}
      </div>
    </div>
  )
}

function ManualEntryModal({ projectId, onClose, onSaved }) {
  const t = useAppT()
  const toast = useToast()
  const typeMeta = getTypeMeta(t)
  const today = new Date().toISOString().split('T')[0]
  const [form, setForm] = useState({ version_tag: '', entry_date: today, entry_type: 'feature', title: '', description: '' })
  const validation = useFormValidation(manualEntrySchema)

  const { mutate: save, isPending } = useMutation({
    mutationFn: (data) => api.post(`/projects/${projectId}/changelog`, data),
    onSuccess: () => { validation.setErrors({}); onSaved(); onClose() },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    save(result.data)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
        <div>
          <label style={lbStyle}>{t('changelog.version_tag')}</label>
          <input value={form.version_tag} onChange={e => { setForm(f => ({ ...f, version_tag: e.target.value })); validation.clearFieldError('version_tag') }} style={validation.inputStyle(inputStyle, 'version_tag')} placeholder={t('changelog.version_tag_ph')} />
        </div>
        <div>
          <label style={lbStyle}>{t('changelog.date')}</label>
          <input type="date" value={form.entry_date} onChange={e => { setForm(f => ({ ...f, entry_date: e.target.value })); validation.clearFieldError('entry_date') }} style={validation.inputStyle(inputStyle, 'entry_date')} />
          {validation.errors.entry_date && <p style={{ marginTop: 4, fontSize: 11, color: 'var(--danger)' }}>{validation.errors.entry_date}</p>}
        </div>
        <div>
          <label style={lbStyle}>{t('changelog.type')}</label>
          <select value={form.entry_type} onChange={e => { setForm(f => ({ ...f, entry_type: e.target.value })); validation.clearFieldError('entry_type') }} style={validation.inputStyle(inputStyle, 'entry_type')}>
            {Object.entries(typeMeta).map(([k, v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
          </select>
        </div>
      </div>
      <div>
        <label style={lbStyle}>{t('changelog.title_label')}</label>
        <input value={form.title} onChange={e => { setForm(f => ({ ...f, title: e.target.value })); validation.clearFieldError('title') }} style={validation.inputStyle(inputStyle, 'title')} placeholder={t('changelog.title_ph')} />
        {validation.errors.title && <p style={{ marginTop: 4, fontSize: 11, color: 'var(--danger)' }}>{validation.errors.title}</p>}
      </div>
      <div>
        <label style={lbStyle}>{t('changelog.description')}</label>
        <textarea value={form.description} onChange={e => { setForm(f => ({ ...f, description: e.target.value })); validation.clearFieldError('description') }} rows={3} style={validation.inputStyle({ ...inputStyle, resize: 'vertical' }, 'description')} placeholder={t('changelog.description_ph')} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <Button variant="secondary" onClick={onClose}>{t('changelog.cancel')}</Button>
        <Button onClick={submit} disabled={isPending}>{isPending ? t('changelog.saving') : t('changelog.add_entry')}</Button>
      </div>
    </div>
  )
}

function GenerateModal({ projectId, onClose, onSaved }) {
  const t = useAppT()
  const toast = useToast()
  const [weeks, setWeeks] = useState(2)
  const [versionTag, setVersionTag] = useState('')
  const validation = useFormValidation(generateSchema)

  const [genResult, setGenResult] = useState(null)

  const { mutate: generate, isPending } = useMutation({
    mutationFn: ({ weeks: validWeeks, version_tag }) => api.post(`/projects/${projectId}/changelog/generate`, { weeks: validWeeks, version_tag: version_tag || null }),
    onSuccess: (res) => { setGenResult(res.data); onSaved() },
    onError: e => toast.error(extractErr(e, 'Error al generar')),
  })

  const submitGenerate = () => {
    const result = validation.validateForm({ weeks, version_tag: versionTag })
    if (!result.success) return
    generate(result.data)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ background: 'rgba(79,142,247,0.08)', border: '1px solid rgba(79,142,247,0.2)', borderRadius: 8, padding: '10px 14px', fontSize: 12, color: 'var(--accent)' }}>
        {t('changelog.generate_info')}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <label style={lbStyle}>{t('changelog.period_weeks')}</label>
          <input type="number" value={weeks} onChange={e => { setWeeks(e.target.value); validation.clearFieldError('weeks') }} min={1} max={52} style={validation.inputStyle(inputStyle, 'weeks')} />
          {validation.errors.weeks && <p style={{ marginTop: 4, fontSize: 11, color: 'var(--danger)' }}>{validation.errors.weeks}</p>}
        </div>
        <div>
          <label style={lbStyle}>{t('changelog.version_tag_optional')}</label>
          <input value={versionTag} onChange={e => { setVersionTag(e.target.value); validation.clearFieldError('version_tag') }} style={validation.inputStyle(inputStyle, 'version_tag')} placeholder={t('changelog.version_tag_ph')} />
        </div>
      </div>
      {genResult && genResult.generated > 0 && (
        <div style={{ background: 'rgba(74,222,128,0.1)', border: '1px solid rgba(74,222,128,0.3)', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: 'var(--success)', fontWeight: 600 }}>
          {t('changelog.generated_success', {count: genResult.generated, weeks: genResult.period_weeks})}
        </div>
      )}
      {genResult && genResult.generated === 0 && (
        <div style={{ background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.3)', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: 'var(--warning)', fontWeight: 500 }}>
          {t('changelog.generated_empty', {message: genResult.message})}
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <Button variant="secondary" onClick={onClose}>{genResult ? t('changelog.close') : t('changelog.cancel')}</Button>
        {!genResult && <Button onClick={submitGenerate} disabled={isPending}>{isPending ? t('changelog.generating') : t('changelog.generate')}</Button>}
      </div>
    </div>
  )
}

export default function ChangelogPage() {
  const t = useAppT()
  const typeMeta = getTypeMeta(t)
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [showManual, setShowManual] = useState(false)
  const [showGenerate, setShowGenerate] = useState(false)

  const { data: projRaw = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })
  const projects = Array.isArray(projRaw) ? projRaw : []

  const { data: changelog, isLoading } = useQuery({
    queryKey: ['changelog', selectedProject, typeFilter],
    queryFn: () => api.get(`/projects/${selectedProject}/changelog`, {
      params: typeFilter !== 'all' ? { entry_type: typeFilter } : undefined,
    }).then(r => r.data),
    enabled: !!selectedProject,
  })

  const { mutate: deleteEntry } = useMutation({
    mutationFn: (id) => api.delete(`/projects/${selectedProject}/changelog/${id}`),
    onSuccess: () => qc.invalidateQueries(['changelog', selectedProject]),
    onError: e => toast.error(extractErr(e, 'Error al eliminar')),
  })

  const invalidate = () => qc.invalidateQueries(['changelog', selectedProject])
  const entries = changelog?.entries || []

  return (
    <div style={{ padding: 32 }}>
      <PageHeader title={t('changelog.title')} subtitle={t('changelog.subtitle')} icon={<ScrollText size={18} />} />

      {/* Project selector + actions */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, alignItems: 'center', flexWrap: 'wrap' }}>
        <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
          style={{ flex: 1, maxWidth: 380, background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
          <option value="">{t('changelog.select_project')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </select>
        {selectedProject && (
          <>
            <Button variant="secondary" onClick={() => setShowGenerate(true)}>{t('changelog.generate')}</Button>
            <Button onClick={() => setShowManual(true)}>{t('changelog.add_entry')}</Button>
          </>
        )}
      </div>

      {/* Type filter pills */}
      {selectedProject && (
        <div style={{ display: 'flex', gap: 6, marginBottom: 20, flexWrap: 'wrap' }}>
          <button onClick={() => setTypeFilter('all')}
            style={{ padding: '5px 14px', borderRadius: 20, border: '1px solid var(--surface-4)', background: typeFilter === 'all' ? 'var(--accent-muted)' : 'var(--surface-2)', color: typeFilter === 'all' ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {t('changelog.all')} ({entries.length})
          </button>
          {Object.entries(typeMeta).map(([k, v]) => {
            const count = entries.filter(e => e.entry_type === k).length
            return count > 0 ? (
              <button key={k} onClick={() => setTypeFilter(k)}
                style={{ padding: '5px 14px', borderRadius: 20, border: `1px solid ${typeFilter === k ? v.color + '60' : 'var(--surface-4)'}`, background: typeFilter === k ? v.bg : 'var(--surface-2)', color: typeFilter === k ? v.color : 'var(--text-2)', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
                {v.icon} {v.label} ({count})
              </button>
            ) : null
          })}
        </div>
      )}

      {!selectedProject ? (
        <EmptyState icon="📋" title={t('changelog.empty_title')} description={t('changelog.empty_desc')} />
      ) : isLoading ? (
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '40px 0' }}><Spinner /><span style={{ color: 'var(--text-2)' }}>{t('changelog.loading')}</span></div>
      ) : entries.length === 0 ? (
        <EmptyState icon="📝" title={t('changelog.empty_title')}
          description={t('changelog.empty_desc')}
          action={<button className="btn-primary" onClick={() => setShowGenerate(true)} style={{ fontSize: 13, padding: '8px 20px' }}>{t('changelog.generate')}</button>}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {entries.map(e => <EntryCard key={e.id} entry={e} onDelete={deleteEntry} />)}
        </div>
      )}

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
    </div>
  )
}
