/**
 * ProjectTemplatesPage — Manage and instantiate project templates.
 * Templates predefine phases, tasks, risks and deliverables for fast project creation.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Spinner } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'

const PHASE_COLOR = '#6366F1'
const TASK_COLOR  = '#10B981'
const RISK_COLOR  = '#F59E0B'
const DELIV_COLOR = '#3B82F6'

function Badge({ color, label }) {
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 4,
      background: `${color}20`, color,
    }}>{label}</span>
  )
}

function TemplateCard({ tpl, onInstantiate, t }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
      borderRadius: 12, padding: 20, transition: 'box-shadow .15s',
    }}
      onMouseEnter={e => e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,.08)'}
      onMouseLeave={e => e.currentTarget.style.boxShadow = 'none'}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-1)' }}>{tpl.name}</div>
          {tpl.description && (
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 3, maxWidth: 380 }}>
              {tpl.description}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          {tpl.estimated_weeks && (
            <Badge color="#6B7280" label={`${tpl.estimated_weeks}${t('project_templates.weeks_abbr')}`} />
          )}
          {tpl.estimated_hours && (
            <Badge color="#6B7280" label={`${tpl.estimated_hours}h`} />
          )}
        </div>
      </div>

      {/* Stats row */}
      <div style={{ display: 'flex', gap: 14, marginBottom: 14, flexWrap: 'wrap' }}>
        {tpl.phases?.length > 0     && <Badge color={PHASE_COLOR} label={`${tpl.phases.length} ${t('projects.phases').toLowerCase()}`} />}
        {tpl.tasks?.length > 0      && <Badge color={TASK_COLOR}  label={`${tpl.tasks.length} ${t('tasks.title').toLowerCase()}`} />}
        {tpl.risks?.length > 0      && <Badge color={RISK_COLOR}  label={`${tpl.risks.length} ${t('risks.title').toLowerCase()}`} />}
        {tpl.deliverables?.length > 0 && <Badge color={DELIV_COLOR} label={`${tpl.deliverables.length} ${t('project_templates.deliverables').toLowerCase()}`} />}
      </div>

      <div style={{ display: 'flex', gap: 10 }}>
        <button
          onClick={() => setExpanded(v => !v)}
          style={{
            padding: '6px 14px', borderRadius: 7, border: '1px solid var(--surface-4)',
            background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12,
          }}
        >
          {expanded ? t('project_templates.hide_detail') : t('project_templates.view_detail')}
        </button>
        <button
          onClick={() => onInstantiate(tpl)}
          style={{
            padding: '6px 14px', borderRadius: 7, border: 'none',
            background: 'var(--accent)', color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 700,
          }}
        >
          {t('project_templates.create_from_template')}
        </button>
      </div>

      {expanded && (
        <div style={{ marginTop: 16, borderTop: '1px solid var(--surface-4)', paddingTop: 14 }}>
          {/* Phases */}
          {tpl.phases?.map((phase, i) => (
            <div key={i} style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: PHASE_COLOR, marginBottom: 4 }}>
                {t('project_templates.phase')} {phase.phase_order}: {phase.name}
              </div>
              {phase.tasks?.map((task, j) => (
                <div key={j} style={{
                  fontSize: 11, color: 'var(--text-2)', paddingLeft: 14,
                  display: 'flex', gap: 8, alignItems: 'center', marginBottom: 2,
                }}>
                  <span style={{ color: TASK_COLOR }}>●</span>
                  {task.title}
                  {task.estimated_hours && <span style={{ color: 'var(--text-3)' }}>({task.estimated_hours}h)</span>}
                </div>
              ))}
            </div>
          ))}
          {/* Risks */}
          {tpl.risks?.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: RISK_COLOR, marginBottom: 4 }}>{t('project_templates.predefined_risks')}</div>
              {tpl.risks.map((risk, i) => (
                <div key={i} style={{ fontSize: 11, color: 'var(--text-2)', paddingLeft: 14, marginBottom: 2, display: 'flex', gap: 8 }}>
                  <span style={{ color: RISK_COLOR }}>▲</span>{risk.title}
                </div>
              ))}
            </div>
          )}
          {/* Deliverables */}
          {tpl.deliverables?.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: DELIV_COLOR, marginBottom: 4 }}>{t('project_templates.deliverables')}</div>
              {tpl.deliverables.map((d, i) => (
                <div key={i} style={{ fontSize: 11, color: 'var(--text-2)', paddingLeft: 14, marginBottom: 2, display: 'flex', gap: 8 }}>
                  <span style={{ color: DELIV_COLOR }}>◆</span>{d.title}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Modal: instantiate template ───────────────────────────────────────────────

function InstantiateModal({ tpl, onClose, onDone, t }) {
  const [projectName, setProjectName] = useState(tpl?.name || '')
  const [clientName, setClientName] = useState('')
  const [startDate, setStartDate] = useState('')
  const [error, setError] = useState(null)

  const mutation = useMutation({
    mutationFn: (data) => api.post(`/templates/${tpl.id}/instantiate`, data),
    onSuccess: (res) => {
      onDone(res.data)
    },
    onError: (err) => {
      setError(err.response?.data?.detail || t('project_templates.creation_error'))
    },
  })

  const submit = () => {
    if (!projectName.trim()) return setError(t('project_templates.project_name_required'))
    mutation.mutate({
      project_name: projectName.trim(),
      client_name: clientName.trim() || undefined,
      start_date: startDate || undefined,
    })
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.55)', zIndex: 9999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--surface-1)', borderRadius: 14, padding: 32, width: 480,
        maxWidth: '95vw', boxShadow: '0 20px 60px rgba(0,0,0,.3)',
      }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-1)', marginBottom: 20 }}>
          {t('project_templates.create_project_from')} «{tpl?.name}»
        </div>

        <label style={{ display: 'block', marginBottom: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 5 }}>
            {t('project_templates.project_name_label')}
          </div>
          <input
            value={projectName}
            onChange={e => setProjectName(e.target.value)}
            placeholder={t('project_templates.project_name_placeholder')}
            style={{
              width: '100%', padding: '8px 12px', borderRadius: 8,
              border: '1px solid var(--surface-4)', background: 'var(--surface-2)',
              color: 'var(--text-1)', fontSize: 13, boxSizing: 'border-box',
            }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 5 }}>
            {t('project_templates.client_label')}
          </div>
          <input
            value={clientName}
            onChange={e => setClientName(e.target.value)}
            placeholder={t('project_templates.client_placeholder')}
            style={{
              width: '100%', padding: '8px 12px', borderRadius: 8,
              border: '1px solid var(--surface-4)', background: 'var(--surface-2)',
              color: 'var(--text-1)', fontSize: 13, boxSizing: 'border-box',
            }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 5 }}>
            {t('project_templates.start_date_label')}
          </div>
          <input
            type="date"
            value={startDate}
            onChange={e => setStartDate(e.target.value)}
            style={{
              width: '100%', padding: '8px 12px', borderRadius: 8,
              border: '1px solid var(--surface-4)', background: 'var(--surface-2)',
              color: 'var(--text-1)', fontSize: 13, boxSizing: 'border-box',
            }}
          />
        </label>

        {error && (
          <div style={{
            padding: '8px 12px', borderRadius: 8, background: 'color-mix(in srgb, var(--danger) 10%, transparent)',
            color: 'var(--danger)', fontSize: 13, marginBottom: 14,
          }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 18px', borderRadius: 8, border: '1px solid var(--surface-4)',
              background: 'transparent', color: 'var(--text-2)', cursor: 'pointer',
            }}
          >
            {t('project_templates.cancel')}
          </button>
          <button
            onClick={submit}
            disabled={mutation.isPending}
            style={{
              padding: '8px 18px', borderRadius: 8, border: 'none',
              background: 'var(--accent)', color: '#fff', cursor: 'pointer', fontWeight: 700,
            }}
          >
            {mutation.isPending ? t('project_templates.creating') : t('project_templates.create_project')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ProjectTemplatesPage() {
  const t = useAppT()
  const queryClient = useQueryClient()
  const [selectedTpl, setSelectedTpl] = useState(null)
  const [successMsg, setSuccessMsg] = useState(null)

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['project-templates'],
    queryFn: () => api.get('/templates').then(r => r.data),
  })

  const handleInstantiateSuccess = (result) => {
    setSelectedTpl(null)
    setSuccessMsg(
      t('project_templates.created_ok')
        .replace('{project_name}', result.project_name)
        .replace('{project_code}', result.project_code)
    )
    queryClient.invalidateQueries({ queryKey: ['projects'] })
    setTimeout(() => setSuccessMsg(null), 6000)
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 900, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-1)', marginBottom: 4 }}>
          {t('project_templates.title')}
        </h1>
        <p style={{ fontSize: 14, color: 'var(--text-3)', margin: 0 }}>
          {t('project_templates.subtitle')}
        </p>
      </div>

      {/* Success banner */}
      {successMsg && (
        <div style={{
          padding: '12px 18px', borderRadius: 10, background: 'color-mix(in srgb, var(--success) 10%, transparent)',
          border: '1px solid color-mix(in srgb, var(--success) 25%, transparent)', color: 'var(--success)', fontSize: 14,
          marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          {successMsg}
          <button onClick={() => setSuccessMsg(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--success)', fontSize: 18 }}>×</button>
        </div>
      )}

      {isLoading ? (
        <div style={{ textAlign: 'center', paddingTop: 60 }}><Spinner /></div>
      ) : templates.length === 0 ? (
        <div style={{
          textAlign: 'center', paddingTop: 60, color: 'var(--text-3)',
        }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>📋</div>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>{t('project_templates.empty_title')}</div>
          <div style={{ fontSize: 13 }}>
            {t('project_templates.empty_subtitle')}
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {templates.map(tpl => (
            <TemplateCard
              key={tpl.id}
              tpl={tpl}
              onInstantiate={setSelectedTpl}
              t={t}
            />
          ))}
        </div>
      )}

      {selectedTpl && (
        <InstantiateModal
          tpl={selectedTpl}
          onClose={() => setSelectedTpl(null)}
          onDone={handleInstantiateSuccess}
          t={t}
        />
      )}
    </div>
  )
}
