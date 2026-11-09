import { useState } from 'react'
import type { CSSProperties, ChangeEvent } from 'react'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { meetingsAIApi } from '../services/api'
import { Button, Spinner, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Video } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'

interface MeetingAction {
  id: string | number
  description?: string
  assignee_name?: string
  due_date_text?: string
  priority?: string
  is_created?: boolean
}

interface MeetingItem {
  id: string | number
  title?: string
  platform?: string
  meeting_date?: string
  created_at?: string
  status?: string
  actions_count?: number
  created_actions?: number
}

interface MeetingDetail extends MeetingItem {
  summary?: string
  duration_minutes?: number
  decisions?: string[]
  actions?: MeetingAction[]
}

interface ProcessFormState {
  title: string
  transcript: string
  platform: string
  participants: string
  duration_minutes: string
}

interface CreateTasksResponse {
  tasks_created?: number
}

const card: CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--surface-4)',
  borderRadius: 'var(--radius-lg)',
}
const fs: CSSProperties = {
  width: '100%',
  background: 'var(--surface-1)',
  border: '1px solid var(--surface-4)',
  borderRadius: 'var(--radius-md)',
  padding: 'var(--space-3) var(--space-3)',
  color: 'var(--text-1)',
  fontSize: '13px',
  outline: 'none',
  fontFamily: 'var(--font-sans)',
  boxSizing: 'border-box',
}
const ls: CSSProperties = {
  fontSize: '11px',
  fontWeight: 700,
  color: 'var(--text-2)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  display: 'block',
  marginBottom: 'var(--space-1)',
}

const PLATFORMS = [
  { id: 'teams',  label: 'Microsoft Teams', icon: '💠' },
  { id: 'zoom',   label: 'Zoom',            icon: '📹' },
  { id: 'meet',   label: 'Google Meet',     icon: '🎥' },
  { id: 'slack',  label: 'Slack Huddle',    icon: '💬' },
  { id: 'presencial', label: 'Presencial',  icon: '👥' },
  { id: 'otro',   label: 'Otro',            icon: '🎙' },
]

const DEMO_TRANSCRIPT = `Pedro: Buenas, arrancamos. El objetivo de hoy es revisar el estado del Q3 y planificar el Q4.
María: Tengo los datos de rendimiento. Estamos al 78% de las entregas planificadas. Hay dos proyectos en riesgo.
Pedro: ¿Cuáles?
María: Alpha está retrasado por los problemas de infraestructura. Carlos, ¿puedes revisar eso esta semana?
Carlos: Sí, lo tengo en el radar. Lo resolveré antes del viernes.
Pedro: Bien. Y el proyecto Beta, necesitamos actualizar el contrato con el cliente antes del 30 de este mes. Ana, ¿puedes encargarte?
Ana: Confirmado, lo gestiono yo.
Pedro: Siguiente punto: el equipo necesita formación en las nuevas herramientas de testing. Luis, ¿coordinas tú con RRHH?
Luis: Sin problema, esta semana lo organizo.
Pedro: Resumiendo: Carlos revisa infraestructura de Alpha antes del viernes, Ana actualiza el contrato de Beta antes del 30, y Luis organiza la formación. Cerramos.`

function ProcessModal({ onClose }: { onClose: () => void }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState<ProcessFormState>({ title: '', transcript: '', platform: 'teams', participants: '', duration_minutes: '' })
  const s = (k: keyof ProcessFormState) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const { mutate: process, isPending } = useMutation({
    mutationFn: (d: ProcessFormState) => meetingsAIApi.process(d as unknown as Record<string, unknown>).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-meetings'] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, t('meetings_ai.error_process'))),
  })

  return (
    <Modal open title={t('meetings_ai.process_title')} onClose={onClose} width={700}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(240px, 100%), 1fr))', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>{t('meetings_ai.title_label')}</label>
          <input value={form.title} onChange={s('title')} style={fs} placeholder={t('meetings_ai.title_placeholder')} />
        </div>

        <div>
          <label style={ls}>{t('meetings_ai.platform_label')}</label>
          <select value={form.platform} onChange={s('platform')} style={fs}>
            {PLATFORMS.map(p => <option key={p.id} value={p.id}>{p.icon} {p.label}</option>)}
          </select>
        </div>

        <div>
          <label style={ls}>{t('meetings_ai.duration_label')}</label>
          <input type="number" value={form.duration_minutes} onChange={s('duration_minutes')} style={fs} placeholder={t('meetings_ai.duration_placeholder')} />
        </div>

        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>{t('meetings_ai.participants_label')}</label>
          <input value={form.participants} onChange={s('participants')} style={fs} placeholder={t('meetings_ai.participants_placeholder')} />
        </div>

        <div style={{ gridColumn: '1/-1' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
            <label style={{ ...ls, marginBottom: 0 }}>{t('meetings_ai.transcript_label')}</label>
            <button onClick={() => setForm(f => ({ ...f, transcript: DEMO_TRANSCRIPT, title: f.title || t('meetings_ai.demo_title'), participants: t('meetings_ai.demo_participants') }))}
              style={{ background: 'transparent', border: 'none', fontSize: "var(--text-xs)", color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit' }}>
              📋 {t('meetings_ai.use_demo')}
            </button>
          </div>
          <textarea value={form.transcript} onChange={s('transcript')} rows={10}
            style={{ ...fs, resize: 'vertical', lineHeight: 1.5 }}
            placeholder={t('meetings_ai.transcript_placeholder')} />
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>{t('meetings_ai.cancel')}</Button>
        <Button onClick={() => process(form)} disabled={isPending || !form.transcript.trim() || !form.title.trim()}>
          {isPending ? t('meetings_ai.processing') : t('meetings_ai.process_btn')}
        </Button>
      </div>
    </Modal>
  )
}

export default function MeetingsAIPage() {
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const _t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showProcess, setShowProcess] = useState(false)
  const [selected, setSelected] = useState<string | number | null>(null)

  const { data: meetingsRaw = [], isLoading } = useQuery({
    queryKey: ['ai-meetings'],
    queryFn: () => meetingsAIApi.list().then(r => r.data),
  })
  const meetings = meetingsRaw as MeetingItem[]
  const { data: detailRaw } = useQuery({
    queryKey: ['ai-meeting', selected],
    queryFn: () => meetingsAIApi.get(selected).then(r => r.data),
    enabled: !!selected,
  })
  const detail = (detailRaw ?? null) as MeetingDetail | null
  const { mutate: createTasks, isPending: creating } = useMutation({
    mutationFn: (id: string | number) => meetingsAIApi.createTasks(id).then(r => r.data),
    onSuccess: (data: CreateTasksResponse) => { qc.invalidateQueries({ queryKey: ['ai-meeting', selected] }); toast.success(`✅ ${data.tasks_created || 0} tareas creadas en Contecflow`) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const platCfg = (p?: string) => PLATFORMS.find((x) => x.id === p) || PLATFORMS[PLATFORMS.length - 1]

  return (
    <PageShell>
      <PageHeader
        icon={<Video size={18} />}
        title={_t('meetings_ai.title')}
        subtitle={_t('meetings_ai.subtitle')}
        actions={<Button onClick={() => setShowProcess(true)}>＋ {_t('meetings_ai.process_meeting')}</Button>}
      showListExport={false}
      />

      {meetings.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(160px, 100%), 1fr))', gap: 12, marginBottom: 24 }}>
            {[
              { icon: '🎙', label: _t('meetings_ai.stats_meetings'), value: meetings.length, color: 'var(--accent)' },
              { icon: '📋', label: _t('meetings_ai.stats_actions'), value: meetings.reduce((a, m) => a + (m.actions_count || 0), 0), color: 'var(--warning)' },
              { icon: '✅', label: _t('meetings_ai.stats_created'), value: meetings.reduce((a, m) => a + (m.created_actions || 0), 0), color: 'var(--success)' },
            ].map(k => (
            <div key={k.label} style={{ ...card, padding: '14px 18px', display: 'flex', gap: 12, alignItems: 'center' }}>
              <span style={{ fontSize: "var(--text-2xl)" }}>{k.icon}</span>
              <div>
                <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: k.color }}>{k.value}</div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{k.label}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: isNarrow ? 'minmax(0, 1fr)' : '300px minmax(0, 1fr)', gap: 20 }}>
        {/* List */}
        <div style={{ minWidth: 0 }}>
          {isLoading ? <Spinner /> : meetings.length === 0 ? (
            <div style={{ ...card, padding: 32, textAlign: 'center' }}>
              <div style={{ fontSize: "var(--text-4xl)", marginBottom: 12 }}>🎙</div>
              <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 6 }}>{_t('meetings_ai.empty_title')}</div>
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 16 }}>{_t('meetings_ai.empty_desc')}</div>
              <Button onClick={() => setShowProcess(true)}>{_t('meetings_ai.empty_btn')}</Button>
            </div>
          ) : meetings.map(m => {
            const plat = platCfg(m.platform)
            return (
              <button key={m.id} type="button" onClick={() => setSelected(m.id)}
                style={{ ...card, padding: '14px 16px', marginBottom: 10, cursor: 'pointer', borderColor: selected === m.id ? 'var(--accent)' : 'var(--surface-4)', background: selected === m.id ? 'var(--accent-muted)' : 'var(--surface-2)', width: '100%', textAlign: 'left', fontFamily: 'inherit' }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 8 }}>
                  <span style={{ fontSize: "var(--text-lg-em)" }}>{plat.icon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.title}</div>
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2 }}>{m.meeting_date?.slice(0, 10) || m.created_at?.slice(0, 10)}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: "var(--text-xs)", padding: '2px 8px', borderRadius: 12, background: m.status === 'done' ? 'var(--success-bg)' : 'var(--warning-bg)', color: m.status === 'done' ? 'var(--success)' : 'var(--warning)', fontWeight: 600 }}>
                    {m.status === 'done' ? _t('meetings_ai.status_done') : _t('meetings_ai.status_processing')}
                  </span>
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{(m.actions_count || 0)} {_t('meetings_ai.actions_label')}</span>
                  {(m.created_actions || 0) > 0 && (
                    <span style={{ fontSize: "var(--text-xs)", color: 'var(--success)' }}>{m.created_actions} {_t('meetings_ai.created_label')}</span>
                  )}
                </div>
              </button>
            )
          })}
        </div>

        {/* Detail */}
        <div style={{ minWidth: 0 }}>
          {!selected ? (
            <div style={{ ...card, padding: 48, textAlign: 'center' }}>
              <div style={{ fontSize: "var(--text-6xl)", marginBottom: 16 }}>🎙</div>
              <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700, marginBottom: 6 }}>{_t('meetings_ai.select_title')}</div>
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{_t('meetings_ai.select_desc')}</div>
            </div>
          ) : !detail ? <Spinner /> : (
            <div>
              {/* Header */}
              <div style={{ ...card, padding: '18px 22px', marginBottom: 14 }}>
                <div style={{ fontSize: "var(--text-lg)", fontWeight: 800, marginBottom: 6 }}>{detail.title}</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                  {detail.platform && <span>{platCfg(detail.platform).icon} {platCfg(detail.platform).label}</span>}
                  {detail.duration_minutes && <span>⏱ {detail.duration_minutes} min</span>}
                  <span>📅 {detail.meeting_date?.slice(0, 10) || detail.created_at?.slice(0, 10)}</span>
                </div>
              </div>

              {/* Summary */}
              {detail.summary && (
                <div style={{ ...card, padding: '16px 20px', marginBottom: 14 }}>
                  <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>📝 {_t('meetings_ai.summary_label')}</div>
                  <div style={{ fontSize: "var(--text-base)", lineHeight: 1.7, color: 'var(--text-2)' }}>{detail.summary}</div>
                </div>
              )}

              {/* Decisions */}
              {(detail.decisions ?? []).length > 0 && (
                <div style={{ ...card, padding: '16px 20px', marginBottom: 14 }}>
                  <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
                    ✅ {_t('meetings_ai.decisions_label', { count: (detail.decisions ?? []).length })}
                  </div>
                  {(detail.decisions ?? []).map((d, i) => (
                    <div key={i} style={{ display: 'flex', gap: 10, padding: '8px 0', borderBottom: i < (detail.decisions ?? []).length - 1 ? '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)' : 'none', fontSize: "var(--text-base)" }}>
                      <span style={{ color: 'var(--success)', flexShrink: 0, marginTop: 1 }}>◆</span>
                      <span style={{ lineHeight: 1.5 }}>{d}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Actions */}
              {(detail.actions ?? []).length > 0 && (
                <div style={{ ...card, padding: '16px 20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
                    <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      📋 {_t('meetings_ai.actions_label_detail', { count: (detail.actions ?? []).length })}
                    </div>
                    {(detail.actions ?? []).some(a => !a.is_created) && (
                      <Button onClick={() => createTasks(selected)} disabled={creating}>
                        {creating ? _t('meetings_ai.creating_tasks') : _t('meetings_ai.create_tasks_btn')}
                      </Button>
                    )}
                  </div>
                  {(detail.actions ?? []).map(a => (
                    <div key={a.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 0', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)', alignItems: 'flex-start', gap: 12 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: "var(--text-base)", fontWeight: 600, marginBottom: 4 }}>{a.description}</div>
                        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
                          {a.assignee_name && `👤 ${a.assignee_name}`}
                          {a.due_date_text && ` · 📅 ${a.due_date_text}`}
                          {a.priority && ` · ${a.priority}`}
                        </div>
                      </div>
                      <span style={{ fontSize: "var(--text-xs)", padding: '3px 10px', borderRadius: 12, background: a.is_created ? 'var(--success-bg)' : 'var(--surface-3)', color: a.is_created ? 'var(--success)' : 'var(--text-2)', fontWeight: 600, flexShrink: 0 }}>
                        {a.is_created ? _t('meetings_ai.action_created') : _t('meetings_ai.action_pending')}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {showProcess && <ProcessModal onClose={() => setShowProcess(false)} />}
    </PageShell>
  )
}
