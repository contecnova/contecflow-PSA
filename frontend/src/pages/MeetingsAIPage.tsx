import { useAppLang } from '../i18n/AppLangContext'
import { PRODUCT_NAME } from '../constants/brand'
import { useState, useId } from 'react'
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
import './MeetingsAIPage.css'

interface ProcessFormState {
  title: string
  transcript: string
  platform: string
  participants: string
  duration_minutes: string
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

/** Marcas con su nombre propio; las genéricas se traducen (`label` es clave i18n solo si empieza por `pagina_meet.`). */
const PLATFORMS = [
  { id: 'teams',  label: 'Microsoft Teams', icon: '💠' },
  { id: 'zoom',   label: 'Zoom',            icon: '📹' },
  { id: 'meet',   label: 'Google Meet',     icon: '🎥' },
  { id: 'slack',  label: 'Slack Huddle',    icon: '💬' },
  { id: 'presencial', label: 'pagina_meet.presencial',  icon: '👥' },
  { id: 'otro',   label: 'pagina_meet.otro',            icon: '🎙' },
]
const nombreDePlataforma = (label: string, t: (k: string) => string) => (label.startsWith('pagina_meet.') ? t(label) : label)

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
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState<ProcessFormState>({ title: '', transcript: '', platform: 'teams', participants: '', duration_minutes: '' })
  const s = (k: keyof ProcessFormState) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const { mutate: process, isPending } = useMutation({
    // Segunda auditoría 2026-11: se mandaban `participants` como texto y `duration_minutes`;
    // el backend espera una lista y `duration_min`, y respondía 422 siempre.
    mutationFn: (d: ProcessFormState) => meetingsAIApi.process({
      title: d.title.trim(),
      transcript: d.transcript,
      platform: d.platform,
      participants: d.participants.split(',').map(p => p.trim()).filter(Boolean),
      duration_min: d.duration_minutes ? Number(d.duration_minutes) : null,
    }).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-meetings'] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, t('meetings_ai.error_process'))),
  })

  return (
    <Modal open title={t('meetings_ai.process_title')} onClose={onClose} width={700}>
      <div className="meet-grid">
        <div className="u-col-full">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('meetings_ai.title_label')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={s('title')} style={fs} placeholder={t('meetings_ai.title_placeholder')} />
        </div>

        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('meetings_ai.platform_label')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.platform} onChange={s('platform')} style={fs}>
            {PLATFORMS.map(p => <option key={p.id} value={p.id}>{p.icon} {nombreDePlataforma(p.label, t)}</option>)}
          </select>
        </div>

        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{t('meetings_ai.duration_label')}</label>
          <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" value={form.duration_minutes} onChange={s('duration_minutes')} style={fs} placeholder={t('meetings_ai.duration_placeholder')} />
        </div>

        <div className="u-col-full">
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>{t('meetings_ai.participants_label')}</label>
          <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.participants} onChange={s('participants')} style={fs} placeholder={t('meetings_ai.participants_placeholder')} />
        </div>

        <div className="u-col-full">
          <div className="meet-row">
            <label style={{ ...ls, marginBottom: 0 }}>{t('meetings_ai.transcript_label')}</label>
            <button onClick={() => setForm(f => ({ ...f, transcript: DEMO_TRANSCRIPT, title: f.title || t('meetings_ai.demo_title'), participants: t('meetings_ai.demo_participants') }))}
              className="meet-btn">
              📋 {t('meetings_ai.use_demo')}
            </button>
          </div>
          <textarea aria-label={t('meetings_ai.transcript_placeholder')} value={form.transcript} onChange={s('transcript')} rows={10}
            style={{ ...fs, resize: 'vertical', lineHeight: 1.5 }}
            placeholder={t('meetings_ai.transcript_placeholder')} />
        </div>
      </div>

      <div className="meet-row-2">
        <Button variant="secondary" onClick={onClose}>{t('meetings_ai.cancel')}</Button>
        <Button onClick={() => process(form)} disabled={isPending || !form.transcript.trim() || !form.title.trim()}>
          {isPending ? t('meetings_ai.processing') : t('meetings_ai.process_btn')}
        </Button>
      </div>
    </Modal>
  )
}

export default function MeetingsAIPage() {
  const { t } = useAppLang()
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const _t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showProcess, setShowProcess] = useState(false)
  const [selected, setSelected] = useState<string | number | null>(null)

  const { data: meetings = [], isLoading } = useQuery({
    queryKey: ['ai-meetings'],
    queryFn: () => meetingsAIApi.list().then(r => r.data),
  })
  const { data: detail = null } = useQuery({
    queryKey: ['ai-meeting', selected],
    queryFn: () => meetingsAIApi.get(selected).then(r => r.data),
    enabled: !!selected,
  })
  // El detalle no trae fechas: salen de la fila del listado.
  const resumen = meetings.find(m => m.id === selected)
  const { mutate: createTasks, isPending: creating } = useMutation({
    mutationFn: (id: string | number) => meetingsAIApi.createTasks(id).then(r => r.data),
    onSuccess: (data) => { qc.invalidateQueries({ queryKey: ['ai-meeting', selected] }); toast.success(t('pagina_meet.tareas_creadas_en', { v1: data.tasks_created || 0, PRODUCT_NAME })) },
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
        <div className="meet-grid-2">
            {[
              { icon: '🎙', label: _t('meetings_ai.stats_meetings'), value: meetings.length, color: 'var(--accent)' },
              { icon: '📋', label: _t('meetings_ai.stats_actions'), value: meetings.reduce((a, m) => a + (m.actions_count || 0), 0), color: 'var(--warning)' },
              { icon: '✅', label: _t('meetings_ai.stats_created'), value: meetings.reduce((a, m) => a + (m.created_actions || 0), 0), color: 'var(--success)' },
            ].map(k => (
            <div key={k.label} style={{ ...card, padding: '14px 18px', display: 'flex', gap: 12, alignItems: 'center' }}>
              <span className="meet-label">{k.icon}</span>
              <div>
                <div className="meet-box" style={{ color: k.color }}>{k.value}</div>
                <div className="u-text2-xs">{k.label}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className={`meet-grid-3 ${isNarrow ? 'meetings-sx1' : 'meetings-sx2'}`}>
        {/* List */}
        <div className="u-min0">
          {isLoading ? <Spinner /> : meetings.length === 0 ? (
            <div style={{ ...card, padding: 32, textAlign: 'center' }}>
              <div className="meet-box-2">🎙</div>
              <div className="meet-box-3">{_t('meetings_ai.empty_title')}</div>
              <div className="meet-box-4">{_t('meetings_ai.empty_desc')}</div>
              <Button onClick={() => setShowProcess(true)}>{_t('meetings_ai.empty_btn')}</Button>
            </div>
          ) : meetings.map(m => {
            const plat = platCfg(m.platform)
            return (
              <button key={m.id} type="button" onClick={() => setSelected(m.id)}
                style={{ ...card, padding: '14px 16px', marginBottom: 10, cursor: 'pointer', borderColor: selected === m.id ? 'var(--accent)' : 'var(--surface-4)', background: selected === m.id ? 'var(--accent-muted)' : 'var(--surface-2)', width: '100%', textAlign: 'left', fontFamily: 'inherit' }}>
                <div className="meet-row-3">
                  <span className="meet-label-2">{plat.icon}</span>
                  <div className="u-flex1-min0">
                    <div className="meet-box-5">{m.title}</div>
                    <div className="u-text2-xs-mt2">{m.meeting_date?.slice(0, 10) || m.created_at?.slice(0, 10)}</div>
                  </div>
                </div>
                <div className="u-wrap-8">
                  <span className={`meet-label-3 ${m.status === 'done' ? 'meetings-sx3' : 'meetings-sx4'}`}>
                    {m.status === 'done' ? _t('meetings_ai.status_done') : _t('meetings_ai.status_processing')}
                  </span>
                  <span className="u-text2-xs">{(m.actions_count || 0)} {_t('meetings_ai.actions_label')}</span>
                  {(m.created_actions || 0) > 0 && (
                    <span className="meet-label-4">{m.created_actions} {_t('meetings_ai.created_label')}</span>
                  )}
                </div>
              </button>
            )
          })}
        </div>

        {/* Detail */}
        <div className="u-min0">
          {!selected ? (
            <div style={{ ...card, padding: 48, textAlign: 'center' }}>
              <div className="u-empty-icon">🎙</div>
              <div className="meet-box-6">{_t('meetings_ai.select_title')}</div>
              <div className="u-text2-sm">{_t('meetings_ai.select_desc')}</div>
            </div>
          ) : !detail ? <Spinner /> : (
            <div>
              {/* Header */}
              <div style={{ ...card, padding: '18px 22px', marginBottom: 14 }}>
                <div className="meet-box-7">{detail.title}</div>
                <div className="meet-row-4">
                  {detail.platform && <span>{platCfg(detail.platform).icon} {nombreDePlataforma(platCfg(detail.platform).label, t)}</span>}
                  {detail.duration_min != null && <span>⏱ {t('pagina_meet.minutos', { n: detail.duration_min })}</span>}
                  {resumen && <span>📅 {(resumen.meeting_date || resumen.created_at).slice(0, 10)}</span>}
                </div>
              </div>

              {/* Summary */}
              {detail.summary && (
                <div style={{ ...card, padding: '16px 20px', marginBottom: 14 }}>
                  <div className="meet-box-8">📝 {_t('meetings_ai.summary_label')}</div>
                  <div className="meet-box-9">{detail.summary}</div>
                </div>
              )}

              {/* Decisions */}
              {(detail.decisions ?? []).length > 0 && (
                <div style={{ ...card, padding: '16px 20px', marginBottom: 14 }}>
                  <div className="meet-box-8">
                    ✅ {_t('meetings_ai.decisions_label', { count: (detail.decisions ?? []).length })}
                  </div>
                  {(detail.decisions ?? []).map((d, i) => (
                    <div key={i} className={`meet-row-5 ${i < (detail.decisions ?? []).length - 1 ? 'meetings-sx5' : 'meetings-sx6'}`}>
                      <span className="meet-label-5">◆</span>
                      <span className="meet-label-6">{d}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Actions */}
              {(detail.actions ?? []).length > 0 && (
                <div style={{ ...card, padding: '16px 20px' }}>
                  <div className="meet-row-6">
                    <div className="meet-box-10">
                      📋 {_t('meetings_ai.actions_label_detail', { count: (detail.actions ?? []).length })}
                    </div>
                    {(detail.actions ?? []).some(a => !a.is_created) && (
                      <Button onClick={() => createTasks(selected)} disabled={creating}>
                        {creating ? _t('meetings_ai.creating_tasks') : _t('meetings_ai.create_tasks_btn')}
                      </Button>
                    )}
                  </div>
                  {(detail.actions ?? []).map(a => (
                    <div key={a.id} className="meet-row-7">
                      <div className="u-flex1-min0">
                        <div className="meet-box-11">{a.description}</div>
                        <div className="u-text2-xs">
                          {a.assignee_name && `👤 ${a.assignee_name}`}
                          {a.due_date_text && ` · 📅 ${a.due_date_text}`}
                        </div>
                      </div>
                      <span className={`meet-label-7 ${a.is_created ? 'meetings-sx3' : 'meetings-sx7'}`}>
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
